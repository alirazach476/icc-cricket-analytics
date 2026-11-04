"""Collect ESPNcricinfo match schedule pages for registered tournaments."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from src.collectors.base_collector import BaseCollector
from src.parsers.match_list_parser import parse_match_schedule_html
from src.utils.helpers import utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


def schedule_url_from_series_url(series_url: str) -> str:
    """Build the fixtures/results schedule URL from a series home URL."""
    parsed = urlparse(series_url)
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}/match-schedule-fixtures-and-results"


class MatchCollector(BaseCollector):
    """Fetch tournament schedule pages and return discovered match manifests."""

    def collect_tournament_matches(
        self,
        tournament_id: str,
        series_url: str | None,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tournament_id": tournament_id,
            "source_name": "ESPNcricinfo",
            "series_url": series_url,
            "schedule_url": None,
            "collected_at": utc_now_iso(),
            "access_status": "skipped_no_url",
            "matches": [],
            "parse": None,
            "raw_html_path": None,
            "error": None,
        }

        if not series_url:
            result["error"] = "No series source_url"
            return result

        schedule_url = schedule_url_from_series_url(series_url)
        result["schedule_url"] = schedule_url

        cache_path = self.project_root / "data" / "raw" / "tournaments" / tournament_id / "schedule.html"
        series_cache = self.project_root / "data" / "raw" / "tournaments" / tournament_id / "series.html"

        fetch = self.fetch_html(
            schedule_url,
            allow_cache_path=cache_path if use_cache else None,
        )
        result["access_status"] = fetch.access_status
        result["fetch"] = fetch.to_dict()

        html = fetch.content if fetch.ok else None
        used_fallback = False

        if (not html) and use_cache and series_cache.exists():
            # Offline/partial path: parse series homepage recentResults only
            html = series_cache.read_text(encoding="utf-8")
            used_fallback = True
            result["access_status"] = "series_homepage_fallback"
            result["warnings"] = [
                "Schedule page unavailable; using cached series homepage (likely partial)."
            ]
            logger.warning("%s: schedule fetch failed (%s); using series.html fallback", tournament_id, fetch.access_status)

        if not html:
            result["error"] = fetch.error or "No HTML available for match discovery"
            return result

        if fetch.ok and fetch.content and not fetch.from_cache:
            raw_path = self.save_raw_text(
                f"data/raw/tournaments/{tournament_id}",
                "schedule.html",
                fetch.content,
                metadata={
                    "tournament_id": tournament_id,
                    "source_url": schedule_url,
                    "access_status": fetch.access_status,
                },
            )
            result["raw_html_path"] = str(raw_path)
        elif fetch.from_cache:
            result["raw_html_path"] = str(cache_path)

        parsed = parse_match_schedule_html(
            html,
            tournament_id=tournament_id,
            source_url=schedule_url if not used_fallback else series_url,
        )
        if used_fallback:
            for match in parsed.get("matches") or []:
                match["discovery_status"] = "partial_homepage"
            parsed.setdefault("warnings", []).append(
                "Parsed from series homepage fallback; match list may be incomplete."
            )

        result["parse"] = {
            "parse_status": parsed.get("parse_status"),
            "warnings": parsed.get("warnings"),
            "match_count": len(parsed.get("matches") or []),
        }
        result["matches"] = parsed.get("matches") or []

        # Derived JSON artifact (safe to refresh)
        out_dir = self.project_root / "data" / "raw" / "matches" / tournament_id
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "tournament_id": tournament_id,
            "schedule_url": schedule_url,
            "collected_at": result["collected_at"],
            "access_status": result["access_status"],
            "match_count": len(result["matches"]),
            "matches": result["matches"],
            "warnings": parsed.get("warnings"),
        }
        json_path = out_dir / "discovered_matches.json"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        result["raw_json_path"] = str(json_path)

        logger.info(
            "Match discovery %s access=%s matches=%s",
            tournament_id,
            result["access_status"],
            len(result["matches"]),
        )
        return result
