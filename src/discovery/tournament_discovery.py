"""Tournament discovery orchestration (Stage 4).

Validates the registry, attempts ESPNcricinfo series-page collection for each
edition, records access outcomes, and updates manifests / optional DB status.

Does not invent matches or statistics. Stops further live requests if the
source returns 401/403/429.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.collectors.tournament_collector import TournamentCollector
from src.discovery.tournament_registry import (
    TournamentRegistry,
    load_tournament_registry,
    sync_tournament_manifest,
)
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _status_from_access(access_status: str) -> str:
    mapping = {
        "ok": "discovered",
        "cached": "discovered",
        "access_restricted": "access_restricted",
        "robots_disallowed": "blocked_robots",
        "not_found": "source_not_found",
        "skipped_no_url": "missing_source_url",
        "error": "discovery_failed",
        "stopped": "access_restricted",
    }
    return mapping.get(access_status, "discovery_failed")


def discover_tournaments(
    *,
    registry: TournamentRegistry | None = None,
    tournament_ids: list[str] | None = None,
    live: bool = True,
    use_cache: bool = True,
    update_database: bool = False,
) -> dict[str, Any]:
    """Discover / verify all (or selected) registered tournaments."""
    root = get_project_root()
    registry = registry or load_tournament_registry()
    collector = TournamentCollector()

    targets = registry.tournaments
    if tournament_ids:
        wanted = set(tournament_ids)
        targets = [t for t in targets if t.tournament_id in wanted]

    results: list[dict[str, Any]] = []
    started_at = utc_now_iso()

    for tournament in targets:
        if not live:
            results.append(
                {
                    "tournament_id": tournament.tournament_id,
                    "source_url": str(tournament.source_url) if tournament.source_url else None,
                    "access_status": "dry_run",
                    "collection_status": "dry_run",
                    "collected_at": utc_now_iso(),
                }
            )
            continue

        if collector.is_stopped:
            results.append(
                {
                    "tournament_id": tournament.tournament_id,
                    "source_url": str(tournament.source_url) if tournament.source_url else None,
                    "access_status": "stopped",
                    "error": collector.stop_reason,
                    "collection_status": "access_restricted",
                    "collected_at": utc_now_iso(),
                }
            )
            continue

        collected = collector.collect_tournament_page(
            tournament.tournament_id,
            str(tournament.source_url) if tournament.source_url else None,
            use_cache=use_cache,
        )
        access = collected.get("access_status", "error")
        collected["collection_status"] = _status_from_access(access)
        if collected.get("parse"):
            collected["discovered_name"] = collected["parse"].get("discovered_name")
        results.append(collected)

    report = {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "live": live,
        "total_targeted": len(targets),
        "results": results,
        "summary": _summarize(results),
        "collector_stopped": collector.is_stopped,
        "stop_reason": collector.stop_reason,
    }

    report_path = _write_discovery_report(root, report)
    report["report_path"] = str(report_path)
    _update_collection_status_manifest(root, results)
    _apply_registry_collection_statuses(registry, results)
    sync_tournament_manifest(registry, root=root)

    if update_database:
        _update_database_statuses(results)

    logger.info(
        "Tournament discovery finished: %s",
        json.dumps(report["summary"], ensure_ascii=False),
    )
    return report


def _summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "discovered": 0,
        "access_restricted": 0,
        "blocked_robots": 0,
        "source_not_found": 0,
        "missing_source_url": 0,
        "discovery_failed": 0,
        "dry_run": 0,
        "other": 0,
    }
    for row in results:
        # Prefer access_status for operational summary
        status = row.get("access_status") or row.get("collection_status") or "other"
        if status in {"ok", "cached"}:
            summary["discovered"] += 1
        elif status in {"stopped", "access_restricted"}:
            summary["access_restricted"] += 1
        elif status == "not_found":
            summary["source_not_found"] += 1
        elif status == "error":
            summary["discovery_failed"] += 1
        elif status in summary:
            summary[status] += 1
        else:
            summary["other"] += 1
    return summary


def _write_discovery_report(root: Path, report: dict[str, Any]) -> Path:
    directory = ensure_dir(root / "data" / "raw" / "tournaments")
    path = directory / "discovery_report.json"
    # Discovery reports may be overwritten (derived status, not raw source HTML)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _update_collection_status_manifest(root: Path, results: list[dict[str, Any]]) -> None:
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
    rows: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("entity_type") == "tournament" and row.get("entity_id") in {
                    r["tournament_id"] for r in results
                }:
                    continue
                rows.append(row)

    now = utc_now_iso()
    for result in results:
        rows.append(
            {
                "entity_type": "tournament",
                "entity_id": result["tournament_id"],
                "tournament_id": result["tournament_id"],
                "status": result.get("collection_status") or result.get("access_status") or "",
                "source_url": result.get("source_url") or "",
                "attempted_at": result.get("collected_at") or now,
                "completed_at": result.get("collected_at") or now,
                "error_message": result.get("error") or "",
                "notes": result.get("discovered_name") or "",
            }
        )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _apply_registry_collection_statuses(
    registry: TournamentRegistry,
    results: list[dict[str, Any]],
) -> None:
    """Update in-memory registry statuses / verified fields from discovery results.

    CSV manifest is synced by the caller. YAML on disk is not rewritten here.
    number_of_matches is never invented from page metadata.
    """
    by_id = {r["tournament_id"]: r for r in results}
    for tournament in registry.tournaments:
        result = by_id.get(tournament.tournament_id)
        if not result:
            continue
        status = result.get("collection_status")
        if status == "dry_run":
            continue
        if status in {
            "not_started",
            "discovering",
            "collecting",
            "partial",
            "complete",
            "failed",
        }:
            tournament.collection_status = status  # type: ignore[assignment]
        elif status == "discovered":
            tournament.collection_status = "partial"  # type: ignore[assignment]
        elif status in {
            "access_restricted",
            "blocked_robots",
            "discovery_failed",
            "source_not_found",
            "missing_source_url",
        }:
            tournament.collection_status = "failed"  # type: ignore[assignment]

        extracted = ((result.get("parse") or {}).get("extracted_fields")) or {}
        if result.get("access_status") in {"ok", "cached"} and extracted:
            if extracted.get("number_of_teams") and tournament.number_of_teams is None:
                tournament.number_of_teams = int(extracted["number_of_teams"])
            if extracted.get("start_date") and not tournament.start_date:
                tournament.start_date = extracted["start_date"]
            if extracted.get("end_date") and not tournament.end_date:
                tournament.end_date = extracted["end_date"]



def _update_database_statuses(results: list[dict[str, Any]]) -> None:
    try:
        from src.database.connection import session_scope
        from src.database.models import CollectionRun, Tournament
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database update skipped: %s", exc)
        return

    try:
        with session_scope() as session:
            for result in results:
                tournament = session.get(Tournament, result["tournament_id"])
                if tournament is None:
                    continue
                status = result.get("collection_status")
                if status == "discovered":
                    tournament.collection_status = "partial"
                elif status in {
                    "access_restricted",
                    "blocked_robots",
                    "discovery_failed",
                    "source_not_found",
                    "missing_source_url",
                }:
                    tournament.collection_status = "failed"
                run = CollectionRun(
                    pipeline_stage="tournament_discovery",
                    tournament_id=result["tournament_id"],
                    status=result.get("access_status") or "unknown",
                    records_attempted=1,
                    records_succeeded=1 if result.get("access_status") in {"ok", "cached"} else 0,
                    records_failed=0 if result.get("access_status") in {"ok", "cached"} else 1,
                    error_message=result.get("error"),
                )
                session.add(run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not update PostgreSQL discovery status: %s", exc)
