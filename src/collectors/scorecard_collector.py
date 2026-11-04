"""Collect ESPNcricinfo full scorecards for discovered matches."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.collectors.base_collector import BaseCollector
from src.parsers.scorecard_parser import parse_scorecard_html
from src.utils.config import get_project_root
from src.utils.helpers import utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ScorecardCollector(BaseCollector):
    """Fetch and parse match scorecards with raw caching and incremental skips."""

    def collect_match_scorecard(
        self,
        *,
        match_id: str,
        tournament_id: str,
        scorecard_url: str | None,
        use_cache: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "match_id": match_id,
            "tournament_id": tournament_id,
            "scorecard_url": scorecard_url,
            "collected_at": utc_now_iso(),
            "access_status": "skipped_no_url",
            "parse": None,
            "raw_html_path": None,
            "parsed_json_path": None,
            "error": None,
        }

        if not scorecard_url:
            result["error"] = "Missing scorecard_url"
            return result

        raw_dir = self.project_root / "data" / "raw" / "scorecards" / match_id
        html_path = raw_dir / "scorecard.html"
        json_path = raw_dir / "scorecard.json"

        if json_path.exists() and not force:
            try:
                parsed = json.loads(json_path.read_text(encoding="utf-8"))
                result["access_status"] = "already_collected"
                result["parse"] = {
                    "parse_status": parsed.get("parse_status"),
                    "scorecard_status": parsed.get("scorecard_status"),
                    "innings": len(parsed.get("innings") or []),
                    "batting_rows": len(parsed.get("batting_scorecards") or []),
                    "bowling_rows": len(parsed.get("bowling_scorecards") or []),
                }
                result["parsed_json_path"] = str(json_path)
                result["raw_html_path"] = str(html_path) if html_path.exists() else None
                return result
            except json.JSONDecodeError:
                logger.warning("Corrupt scorecard JSON for %s; recollecting", match_id)

        fetch = self.fetch_html(
            scorecard_url,
            allow_cache_path=html_path if use_cache and html_path.exists() else None,
        )
        result["access_status"] = fetch.access_status
        result["fetch"] = fetch.to_dict()
        if not fetch.ok or not fetch.content:
            result["error"] = fetch.error or "Scorecard fetch failed"
            return result

        if not fetch.from_cache:
            saved = self.save_raw_text(
                f"data/raw/scorecards/{match_id}",
                "scorecard.html",
                fetch.content,
                metadata={
                    "match_id": match_id,
                    "tournament_id": tournament_id,
                    "source_url": scorecard_url,
                    "access_status": fetch.access_status,
                },
            )
            result["raw_html_path"] = str(saved)
        else:
            result["raw_html_path"] = str(html_path)

        parsed = parse_scorecard_html(
            fetch.content,
            match_id=match_id,
            tournament_id=tournament_id,
            source_url=scorecard_url,
        )
        parsed["collected_at"] = result["collected_at"]
        raw_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
        result["parsed_json_path"] = str(json_path)
        result["parse"] = {
            "parse_status": parsed.get("parse_status"),
            "scorecard_status": parsed.get("scorecard_status"),
            "innings": len(parsed.get("innings") or []),
            "batting_rows": len(parsed.get("batting_scorecards") or []),
            "bowling_rows": len(parsed.get("bowling_scorecards") or []),
            "warnings": parsed.get("warnings"),
        }
        logger.info(
            "Scorecard %s access=%s innings=%s batting=%s bowling=%s",
            match_id,
            result["access_status"],
            result["parse"]["innings"],
            result["parse"]["batting_rows"],
            result["parse"]["bowling_rows"],
        )
        return result


def load_match_manifest(path: Path | None = None) -> list[dict[str, str]]:
    root = get_project_root()
    manifest = path or (root / "data" / "manifests" / "match_urls.csv")
    with manifest.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def collect_scorecards(
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
    limit: int | None = None,
    use_cache: bool = True,
    force: bool = False,
    live: bool = True,
) -> dict[str, Any]:
    """Collect scorecards for selected matches from the match URL manifest."""
    rows = load_match_manifest()
    if tournament_id:
        rows = [r for r in rows if r.get("tournament_id") == tournament_id]
    if match_ids:
        wanted = set(match_ids)
        rows = [r for r in rows if r.get("match_id") in wanted]
    if limit is not None:
        rows = rows[: max(0, limit)]

    collector = ScorecardCollector()
    started = utc_now_iso()
    results: list[dict[str, Any]] = []

    if not live:
        return {
            "started_at": started,
            "finished_at": utc_now_iso(),
            "live": False,
            "targeted": len(rows),
            "results": [
                {
                    "match_id": r.get("match_id"),
                    "tournament_id": r.get("tournament_id"),
                    "access_status": "dry_run",
                }
                for r in rows
            ],
            "summary": {"dry_run": len(rows)},
        }

    for row in rows:
        if collector.is_stopped:
            results.append(
                {
                    "match_id": row.get("match_id"),
                    "tournament_id": row.get("tournament_id"),
                    "access_status": "stopped",
                    "error": collector.stop_reason,
                }
            )
            continue
        collected = collector.collect_match_scorecard(
            match_id=row["match_id"],
            tournament_id=row.get("tournament_id") or "",
            scorecard_url=row.get("scorecard_url") or None,
            use_cache=use_cache,
            force=force,
        )
        results.append(collected)

    summary = _summarize(results)
    report = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "live": True,
        "targeted": len(rows),
        "results": results,
        "summary": summary,
        "collector_stopped": collector.is_stopped,
        "stop_reason": collector.stop_reason,
    }
    report_path = get_project_root() / "data" / "raw" / "scorecards" / "collection_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    _update_collection_status(results)
    return report


def _summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in results:
        status = row.get("access_status") or "unknown"
        summary[status] = summary.get(status, 0) + 1
    summary["total"] = len(results)
    summary["parsed_ok"] = sum(
        1
        for row in results
        if (row.get("parse") or {}).get("parse_status") == "ok"
        or row.get("access_status") == "already_collected"
    )
    return summary


def _update_collection_status(results: list[dict[str, Any]]) -> None:
    root = get_project_root()
    path = root / "data" / "manifests" / "collection_status.csv"
    fieldnames = [
        "entity_type",
        "entity_id",
        "tournament_id",
        "status",
        "source_url",
        "attempted_at",
        "completed_at",
        "error_message",
        "notes",
    ]
    existing: list[dict[str, str]] = []
    touched = {r.get("match_id") for r in results}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("entity_type") == "scorecard" and row.get("entity_id") in touched:
                    continue
                existing.append(row)
    now = utc_now_iso()
    for row in results:
        existing.append(
            {
                "entity_type": "scorecard",
                "entity_id": row.get("match_id") or "",
                "tournament_id": row.get("tournament_id") or "",
                "status": row.get("access_status") or "",
                "source_url": row.get("scorecard_url") or "",
                "attempted_at": row.get("collected_at") or now,
                "completed_at": row.get("collected_at") or now,
                "error_message": row.get("error") or "",
                "notes": json.dumps(row.get("parse") or {}, ensure_ascii=False),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)
