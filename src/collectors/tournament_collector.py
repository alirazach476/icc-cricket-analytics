"""Collect ESPNcricinfo tournament / series pages for registered editions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.collectors.base_collector import BaseCollector, FetchResult
from src.parsers.tournament_parser import parse_tournament_html
from src.utils.helpers import utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TournamentCollector(BaseCollector):
    """Fetch and persist raw tournament series pages."""

    def collect_tournament_page(
        self,
        tournament_id: str,
        source_url: str | None,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Collect one tournament series page.

        Never fabricates page content. On access restriction, returns a structured failure.
        """
        result: dict[str, Any] = {
            "tournament_id": tournament_id,
            "source_name": "ESPNcricinfo",
            "source_url": source_url,
            "collected_at": utc_now_iso(),
            "access_status": "skipped_no_url",
            "fetch": None,
            "parse": None,
            "raw_html_path": None,
            "raw_json_path": None,
        }

        if not source_url:
            result["access_status"] = "skipped_no_url"
            result["error"] = "No source_url in registry"
            logger.warning("%s has no source_url; skipping", tournament_id)
            return result

        cache_path = (
            Path("data/raw/tournaments") / tournament_id / "series.html"
        )
        cache_abs = self.project_root / cache_path

        fetch: FetchResult = self.fetch_html(
            source_url,
            allow_cache_path=cache_abs if use_cache else None,
        )
        result["fetch"] = fetch.to_dict()
        result["access_status"] = fetch.access_status

        if not fetch.ok or not fetch.content:
            result["error"] = fetch.error
            logger.warning(
                "Tournament collect failed %s status=%s error=%s",
                tournament_id,
                fetch.access_status,
                fetch.error,
            )
            return result

        raw_path = self.save_raw_text(
            f"data/raw/tournaments/{tournament_id}",
            "series.html",
            fetch.content,
            metadata={
                "tournament_id": tournament_id,
                "source_url": source_url,
                "access_status": fetch.access_status,
                "from_cache": fetch.from_cache,
                "status_code": fetch.status_code,
            },
        )
        result["raw_html_path"] = str(raw_path)

        parsed = parse_tournament_html(fetch.content, source_url=source_url)
        result["parse"] = parsed

        payload = {
            "tournament_id": tournament_id,
            "source_name": "ESPNcricinfo",
            "source_url": source_url,
            "collected_at": result["collected_at"],
            "access_status": fetch.access_status,
            "fetch": fetch.to_dict(),
            "parse": parsed,
        }
        # series.json is a derived parse artifact and may be refreshed; raw HTML is not overwritten.
        json_dir = self.project_root / "data" / "raw" / "tournaments" / tournament_id
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / "series.json"
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        result["raw_json_path"] = str(json_path)
        logger.info(
            "Collected tournament %s access=%s name=%s",
            tournament_id,
            fetch.access_status,
            (parsed or {}).get("discovered_name"),
        )
        return result
