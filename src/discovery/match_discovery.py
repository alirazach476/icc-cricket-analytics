"""Match discovery orchestration (Stage 5).

For each registered tournament, fetch the ESPNcricinfo schedule page (or use
cache / series homepage fallback), extract match URLs, and update manifests.
Never fabricates matches.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.collectors.match_collector import MatchCollector
from src.discovery.tournament_registry import load_tournament_registry
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

MATCH_MANIFEST_FIELDS = [
    "match_id",
    "tournament_id",
    "match_number",
    "match_stage",
    "match_date",
    "source_url",
    "scorecard_url",
    "commentary_url",
    "discovery_status",
    "discovered_at",
    "team1_name",
    "team2_name",
    "venue",
    "city",
    "result_type",
    "result_margin",
    "is_cancelled",
    "is_super_over",
    "has_scorecard",
    "has_commentary",
]


def discover_matches(
    *,
    tournament_id: str | None = None,
    tournament_ids: list[str] | None = None,
    live: bool = True,
    use_cache: bool = True,
    update_database: bool = False,
) -> dict[str, Any]:
    """Discover matches for one, many, or all registered tournaments."""
    root = get_project_root()
    registry = load_tournament_registry()
    collector = MatchCollector()

    targets = registry.tournaments
    selected = set(tournament_ids or [])
    if tournament_id:
        selected.add(tournament_id)
    if selected:
        targets = [t for t in targets if t.tournament_id in selected]

    started_at = utc_now_iso()
    tournament_results: list[dict[str, Any]] = []
    all_matches: list[dict[str, Any]] = []

    for tournament in targets:
        if not live:
            tournament_results.append(
                {
                    "tournament_id": tournament.tournament_id,
                    "access_status": "dry_run",
                    "match_count": 0,
                    "matches": [],
                }
            )
            continue

        if collector.is_stopped:
            tournament_results.append(
                {
                    "tournament_id": tournament.tournament_id,
                    "access_status": "stopped",
                    "error": collector.stop_reason,
                    "match_count": 0,
                    "matches": [],
                }
            )
            continue

        series_url = str(tournament.source_url) if tournament.source_url else None
        collected = collector.collect_tournament_matches(
            tournament.tournament_id,
            series_url,
            use_cache=use_cache,
        )
        matches = collected.get("matches") or []
        for match in matches:
            match["discovered_at"] = collected.get("collected_at") or utc_now_iso()
        all_matches.extend(matches)
        tournament_results.append(
            {
                "tournament_id": tournament.tournament_id,
                "access_status": collected.get("access_status"),
                "schedule_url": collected.get("schedule_url"),
                "match_count": len(matches),
                "error": collected.get("error"),
                "warnings": (collected.get("parse") or {}).get("warnings"),
                "raw_json_path": collected.get("raw_json_path"),
            }
        )

        # Update verified match count only when schedule page fully parsed
        if (
            collected.get("access_status") in {"ok", "cached"}
            and matches
            and not any(
                m.get("discovery_status") == "partial_homepage" for m in matches
            )
        ):
            tournament.number_of_matches = len(matches)

    # Merge into persistent match manifest (preserve other tournaments)
    manifest_path = _sync_match_manifest(root, all_matches, replace_tournaments={t.tournament_id for t in targets if live})

    # Refresh tournament manifest with any verified match counts
    from src.discovery.tournament_registry import sync_tournament_manifest

    sync_tournament_manifest(registry, root=root)

    report = {
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "live": live,
        "total_tournaments": len(targets),
        "total_matches_discovered": len(all_matches),
        "tournaments": tournament_results,
        "summary": _summarize(tournament_results, all_matches),
        "manifest_path": str(manifest_path),
        "collector_stopped": collector.is_stopped,
        "stop_reason": collector.stop_reason,
    }
    report_path = ensure_dir(root / "data" / "raw" / "matches") / "discovery_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)

    if update_database and all_matches:
        _update_database_match_counts(tournament_results)

    logger.info(
        "Match discovery finished: tournaments=%s matches=%s",
        len(targets),
        len(all_matches),
    )
    return report


def _summarize(
    tournament_results: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    by_access: dict[str, int] = {}
    for row in tournament_results:
        status = row.get("access_status") or "unknown"
        by_access[status] = by_access.get(status, 0) + 1
    return {
        "tournaments_by_access": by_access,
        "matches_discovered": len(matches),
        "matches_with_scorecard_url": sum(1 for m in matches if m.get("scorecard_url")),
        "matches_with_commentary_url": sum(1 for m in matches if m.get("commentary_url")),
        "cancelled_matches": sum(1 for m in matches if m.get("is_cancelled")),
        "super_over_matches": sum(1 for m in matches if m.get("is_super_over")),
    }


def _sync_match_manifest(
    root: Path,
    new_matches: list[dict[str, Any]],
    *,
    replace_tournaments: set[str],
) -> Path:
    path = root / "data" / "manifests" / "match_urls.csv"
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("tournament_id") in replace_tournaments:
                    continue
                existing.append(row)

    rows = existing
    for match in new_matches:
        rows.append({field: "" if match.get(field) is None else str(match.get(field)) for field in MATCH_MANIFEST_FIELDS})

    # De-duplicate by match_id keeping the latest occurrence
    dedup: dict[str, dict[str, str]] = {}
    for row in rows:
        mid = row.get("match_id")
        if mid:
            dedup[mid] = row
    final_rows = list(dedup.values())
    final_rows.sort(key=lambda r: (r.get("tournament_id") or "", r.get("match_date") or "", r.get("match_id") or ""))

    # Keep columns added by later stages (e.g. ball_by_ball_status) and write atomically:
    # a failure must never truncate the existing manifest.
    extra_fields = []
    for row in final_rows:
        for key in row:
            if key not in MATCH_MANIFEST_FIELDS and key not in extra_fields:
                extra_fields.append(key)
    fieldnames = MATCH_MANIFEST_FIELDS + extra_fields
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(final_rows)
    tmp_path.replace(path)

    logger.info("Synced match manifest with %s rows -> %s", len(final_rows), path)
    return path


def _update_database_match_counts(tournament_results: list[dict[str, Any]]) -> None:
    try:
        from src.database.connection import session_scope
        from src.database.models import CollectionRun, Tournament
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB update skipped: %s", exc)
        return

    try:
        with session_scope() as session:
            for row in tournament_results:
                tid = row["tournament_id"]
                tournament = session.get(Tournament, tid)
                if tournament and row.get("access_status") in {"ok", "cached"} and row.get("match_count"):
                    tournament.number_of_matches = int(row["match_count"])
                    if tournament.collection_status == "not_started":
                        tournament.collection_status = "partial"
                session.add(
                    CollectionRun(
                        pipeline_stage="match_discovery",
                        tournament_id=tid,
                        status=row.get("access_status") or "unknown",
                        records_attempted=1,
                        records_succeeded=1 if row.get("match_count") else 0,
                        records_failed=0 if row.get("match_count") else 1,
                        error_message=row.get("error"),
                    )
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not update PostgreSQL match discovery status: %s", exc)
