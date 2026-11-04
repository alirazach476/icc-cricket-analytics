"""Collect ball-by-ball data from ESPNcricinfo commentary and/or Cricsheet."""

from __future__ import annotations

import csv
import json
from typing import Any

from src.collectors.base_collector import BaseCollector
from src.collectors.cricsheet_collector import CricsheetCollector
from src.collectors.scorecard_collector import load_match_manifest
from src.parsers.ball_by_ball_parser import parse_espn_commentary_html
from src.utils.config import get_project_root
from src.utils.helpers import utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CommentaryCollector(BaseCollector):
    """Fetch ESPN commentary pages (usually partial) for enrichment/status."""

    def collect_match_commentary(
        self,
        *,
        match_id: str,
        tournament_id: str,
        commentary_url: str | None,
        use_cache: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "match_id": match_id,
            "tournament_id": tournament_id,
            "commentary_url": commentary_url,
            "collected_at": utc_now_iso(),
            "access_status": "skipped_no_url",
            "parse": None,
            "error": None,
        }
        if not commentary_url:
            result["error"] = "Missing commentary_url"
            return result

        raw_dir = self.project_root / "data" / "raw" / "commentary" / match_id
        html_path = raw_dir / "commentary.html"
        json_path = raw_dir / "commentary_espn.json"

        if json_path.exists() and not force:
            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            result["access_status"] = "already_collected"
            result["parse"] = {
                "parse_status": parsed.get("parse_status"),
                "ball_by_ball_status": parsed.get("ball_by_ball_status"),
                "delivery_count": len(parsed.get("deliveries") or []),
            }
            result["parsed_json_path"] = str(json_path)
            return result

        fetch = self.fetch_html(
            commentary_url,
            allow_cache_path=html_path if use_cache and html_path.exists() else None,
        )
        result["access_status"] = fetch.access_status
        if not fetch.ok or not fetch.content:
            result["error"] = fetch.error or "Commentary fetch failed"
            return result

        if not fetch.from_cache:
            saved = self.save_raw_text(
                f"data/raw/commentary/{match_id}",
                "commentary.html",
                fetch.content,
                metadata={
                    "match_id": match_id,
                    "tournament_id": tournament_id,
                    "source_url": commentary_url,
                },
            )
            result["raw_html_path"] = str(saved)
        else:
            result["raw_html_path"] = str(html_path)

        parsed = parse_espn_commentary_html(
            fetch.content,
            match_id=match_id,
            source_url=commentary_url,
        )
        raw_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
        result["parsed_json_path"] = str(json_path)
        result["parse"] = {
            "parse_status": parsed.get("parse_status"),
            "ball_by_ball_status": parsed.get("ball_by_ball_status"),
            "delivery_count": len(parsed.get("deliveries") or []),
            "warnings": parsed.get("warnings"),
        }
        return result


def _tournament_format(tournament_id: str) -> str:
    return "ODI" if tournament_id.startswith("ODI_") else "T20"


def collect_commentary(
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
    limit: int | None = None,
    source: str = "both",
    use_cache: bool = True,
    force: bool = False,
    live: bool = True,
) -> dict[str, Any]:
    """Collect ball-by-ball data.

    source:
      - espn: ESPN commentary HTML only (typically partial)
      - cricsheet: Cricsheet WC bundles linked by date/teams
      - both: try Cricsheet for complete BBB; optionally also ESPN for commentary text
    """
    rows = load_match_manifest()
    if tournament_id:
        rows = [r for r in rows if r.get("tournament_id") == tournament_id]
    if match_ids:
        wanted = set(match_ids)
        rows = [r for r in rows if r.get("match_id") in wanted]
    if limit is not None:
        rows = rows[: max(0, limit)]

    started = utc_now_iso()
    results: list[dict[str, Any]] = []
    espn = CommentaryCollector()
    cricsheet = CricsheetCollector()

    if not live:
        return {
            "started_at": started,
            "finished_at": utc_now_iso(),
            "live": False,
            "targeted": len(rows),
            "source": source,
            "results": [{"match_id": r["match_id"], "access_status": "dry_run"} for r in rows],
            "summary": {"dry_run": len(rows)},
        }

    # Prefetch Cricsheet indexes once when needed
    if source in {"cricsheet", "both"}:
        formats_needed = {_tournament_format(r["tournament_id"]) for r in rows if r.get("tournament_id")}
        for fmt in sorted(formats_needed):
            cricsheet.build_index(fmt)

    for row in rows:
        item: dict[str, Any] = {
            "match_id": row["match_id"],
            "tournament_id": row.get("tournament_id"),
            "collected_at": utc_now_iso(),
            "espn": None,
            "cricsheet": None,
            "ball_by_ball_status": "not_checked",
            "primary_source": None,
        }

        if source in {"espn", "both"} and not espn.is_stopped:
            item["espn"] = espn.collect_match_commentary(
                match_id=row["match_id"],
                tournament_id=row.get("tournament_id") or "",
                commentary_url=row.get("commentary_url") or None,
                use_cache=use_cache,
                force=force,
            )
            if espn.is_stopped and source == "espn":
                item["ball_by_ball_status"] = "access_restricted"
                results.append(item)
                continue

        if source in {"cricsheet", "both"}:
            item["cricsheet"] = cricsheet.load_deliveries_for_match(
                match_id=row["match_id"],
                match_format=_tournament_format(row.get("tournament_id") or "ODI"),
                match_date=row.get("match_date") or None,
                team1=row.get("team1_name") or None,
                team2=row.get("team2_name") or None,
            )

        # Precedence: complete Cricsheet > partial ESPN > unavailable
        cs = item.get("cricsheet") or {}
        es = item.get("espn") or {}
        if (cs.get("parse") or {}).get("ball_by_ball_status") == "complete":
            item["ball_by_ball_status"] = "complete"
            item["primary_source"] = "Cricsheet"
        elif (es.get("parse") or {}).get("delivery_count", 0) > 0:
            item["ball_by_ball_status"] = "partial"
            item["primary_source"] = "ESPNcricinfo"
        elif cs.get("access_status") == "ambiguous":
            item["ball_by_ball_status"] = "unavailable"
            item["primary_source"] = None
            item["error"] = cs.get("error")
        else:
            item["ball_by_ball_status"] = "unavailable"

        # Write combined status artifact
        out_dir = get_project_root() / "data" / "raw" / "commentary" / row["match_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "bbb_status.json").write_text(
            json.dumps(item, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        results.append(item)

    summary = _summarize(results)
    report = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "live": True,
        "source": source,
        "targeted": len(rows),
        "results": results,
        "summary": summary,
        "espn_stopped": espn.is_stopped,
        "stop_reason": espn.stop_reason,
    }
    report_path = get_project_root() / "data" / "raw" / "commentary" / "collection_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    _update_collection_status(results)
    _update_match_manifest_bbb_status(results)
    return report


def _summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "complete": 0,
        "partial": 0,
        "unavailable": 0,
        "not_checked": 0,
        "cricsheet_ok": 0,
        "espn_partial": 0,
    }
    for row in results:
        status = row.get("ball_by_ball_status") or "not_checked"
        if status in summary:
            summary[status] += 1
        if (row.get("cricsheet") or {}).get("access_status") == "ok":
            summary["cricsheet_ok"] += 1
        if ((row.get("espn") or {}).get("parse") or {}).get("delivery_count", 0) > 0:
            summary["espn_partial"] += 1
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
                if row.get("entity_type") == "commentary" and row.get("entity_id") in touched:
                    continue
                existing.append(row)
    now = utc_now_iso()
    for row in results:
        existing.append(
            {
                "entity_type": "commentary",
                "entity_id": row.get("match_id") or "",
                "tournament_id": row.get("tournament_id") or "",
                "status": row.get("ball_by_ball_status") or "",
                "source_url": row.get("primary_source") or "",
                "attempted_at": row.get("collected_at") or now,
                "completed_at": row.get("collected_at") or now,
                "error_message": row.get("error") or "",
                "notes": json.dumps(
                    {
                        "cricsheet": (row.get("cricsheet") or {}).get("parse"),
                        "espn": (row.get("espn") or {}).get("parse"),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)


def _update_match_manifest_bbb_status(results: list[dict[str, Any]]) -> None:
    root = get_project_root()
    path = root / "data" / "manifests" / "match_urls.csv"
    if not path.exists():
        return
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys()) if rows else []
    if "ball_by_ball_status" not in fieldnames:
        fieldnames.append("ball_by_ball_status")
    by_id = {r["match_id"]: r.get("ball_by_ball_status") for r in results}
    for row in rows:
        if row.get("match_id") in by_id:
            row["ball_by_ball_status"] = by_id[row["match_id"]] or row.get("ball_by_ball_status", "not_checked")
        else:
            row.setdefault("ball_by_ball_status", row.get("ball_by_ball_status", "not_checked"))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
