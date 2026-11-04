"""Base HTTP collector with robots checks, throttling, caching, and graceful stops."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils.config import get_project_root, get_settings, resolve_path
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

STOP_STATUSES = {401, 403, 429}


@dataclass
class FetchResult:
    """Outcome of a single HTTP fetch attempt."""

    url: str
    ok: bool
    status_code: int | None = None
    content: str | None = None
    content_type: str | None = None
    error: str | None = None
    access_status: str = "unknown"
    fetched_at: str = field(default_factory=utc_now_iso)
    from_cache: bool = False
    raw_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "ok": self.ok,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "error": self.error,
            "access_status": self.access_status,
            "fetched_at": self.fetched_at,
            "from_cache": self.from_cache,
            "raw_path": self.raw_path,
            "content_length": len(self.content) if self.content else 0,
        }


class AccessRestrictedError(RuntimeError):
    """Raised when the source returns a hard stop status (401/403/429)."""


class BaseCollector:
    """Shared collector behaviour for ESPNcricinfo (and similar) HTML pages."""

    def __init__(self) -> None:
        settings = get_settings()
        collection = settings.get("collection", {})
        self.user_agent = collection.get(
            "user_agent",
            "CricketWorldCupAnalytics/0.1 (educational research; local use)",
        )
        self.timeout = float(collection.get("timeout_seconds", 30))
        self.delay = float(collection.get("request_delay_seconds", 1.5))
        self.max_retries = int(collection.get("max_retries", 3))
        self.respect_robots = bool(collection.get("respect_robots_txt", True))
        self.cache_enabled = bool(collection.get("cache_enabled", True))
        self.project_root = get_project_root()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self._last_request_at: float | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self._stop_collection = False
        self._stop_reason: str | None = None

    @property
    def is_stopped(self) -> bool:
        return self._stop_collection

    @property
    def stop_reason(self) -> str | None:
        return self._stop_reason

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _robots_for(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            rp = RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            try:
                self._throttle()
                response = self.session.get(robots_url, timeout=self.timeout)
                self._last_request_at = time.monotonic()
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                else:
                    # Fail closed for unknown robots when respect is required
                    rp.parse(["User-agent: *", "Disallow: /"])
                    logger.warning(
                        "Could not load robots.txt (%s); failing closed for %s",
                        response.status_code,
                        origin,
                    )
            except requests.RequestException as exc:
                rp.parse(["User-agent: *", "Disallow: /"])
                logger.warning("robots.txt fetch failed for %s: %s; failing closed", origin, exc)
            self._robots[origin] = rp
        return self._robots[origin]

    def can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        return bool(self._robots_for(url).can_fetch(self.user_agent, url))

    def _request_once(self, url: str) -> requests.Response:
        self._throttle()
        response = self.session.get(url, timeout=self.timeout)
        self._last_request_at = time.monotonic()
        return response

    def fetch_html(self, url: str, *, allow_cache_path: Path | None = None) -> FetchResult:
        """Fetch HTML. Never bypasses 401/403/429. Optionally returns cached raw HTML."""
        if self._stop_collection:
            return FetchResult(
                url=url,
                ok=False,
                error=self._stop_reason,
                access_status="stopped",
            )

        if allow_cache_path and allow_cache_path.exists() and self.cache_enabled:
            content = allow_cache_path.read_text(encoding="utf-8")
            logger.info("Using cached raw HTML: %s", allow_cache_path)
            return FetchResult(
                url=url,
                ok=True,
                status_code=200,
                content=content,
                content_type="text/html",
                access_status="cached",
                from_cache=True,
                raw_path=str(allow_cache_path),
            )

        if not self.can_fetch(url):
            logger.warning("robots.txt disallows fetch: %s", url)
            return FetchResult(
                url=url,
                ok=False,
                error="Disallowed by robots.txt",
                access_status="robots_disallowed",
            )

        try:
            response = self._fetch_with_retries(url)
        except AccessRestrictedError as exc:
            self._stop_collection = True
            self._stop_reason = str(exc)
            logger.error("Access restricted — stopping further collection: %s", exc)
            return FetchResult(
                url=url,
                ok=False,
                status_code=getattr(exc, "status_code", None),
                error=str(exc),
                access_status="access_restricted",
            )
        except requests.RequestException as exc:
            logger.error("Request failed for %s: %s", url, exc)
            return FetchResult(
                url=url,
                ok=False,
                error=str(exc),
                access_status="error",
            )

        if response.status_code == 404:
            return FetchResult(
                url=url,
                ok=False,
                status_code=404,
                error="Not found",
                access_status="not_found",
            )

        if response.status_code >= 400:
            return FetchResult(
                url=url,
                ok=False,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}",
                access_status="error",
            )

        return FetchResult(
            url=url,
            ok=True,
            status_code=response.status_code,
            content=response.text,
            content_type=response.headers.get("Content-Type"),
            access_status="ok",
        )

    def _fetch_with_retries(self, url: str) -> requests.Response:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=2, min=1, max=20),
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        )
        def _inner() -> requests.Response:
            response = self._request_once(url)
            if response.status_code in STOP_STATUSES:
                err = AccessRestrictedError(
                    f"HTTP {response.status_code} for {url} — collection stopped per source rules"
                )
                err.status_code = response.status_code
                raise err
            return response

        return _inner()

    def save_raw_text(
        self,
        relative_dir: str,
        filename: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Save raw source text without overwriting an existing file."""
        directory = ensure_dir(resolve_path(relative_dir))
        path = directory / filename
        if path.exists():
            logger.info("Raw file exists; not overwriting: %s", path)
            return path
        path.write_text(content, encoding="utf-8")
        if metadata is not None:
            meta_path = path.with_suffix(path.suffix + ".meta.json")
            if not meta_path.exists():
                meta_path.write_text(
                    json.dumps(
                        {
                            **metadata,
                            "saved_at": datetime.now(UTC).isoformat(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
        return path
