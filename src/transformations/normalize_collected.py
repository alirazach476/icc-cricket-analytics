"""Normalize collected raw scorecards / BBB into data/processed (Stage 8)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.collectors.scorecard_collector import load_match_manifest
from src.parsers.batting_parser import parse_batting_from_scorecard
from src.parsers.bowling_parser import parse_bowling_from_scorecard
from src.parsers.fielding_parser import parse_fielding_from_scorecard
from src.parsers.innings_parser import parse_innings_from_scorecard
from src.parsers.match_parser import parse_match_from_scorecard
from src.transformations.clean_deliveries import clean_delivery_list
from src.transformations.clean_players import merge_player_records
from src.transformations.standardize_teams import standardize_team_record
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON %s: %s", path, exc)
        return None


def _bbb_status_and_deliveries(
    root: Path, match_id: str
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Prefer complete Cricsheet deliveries; fall back to ESPN partial."""
    commentary_dir = root / "data" / "raw" / "commentary" / match_id
    status_path = commentary_dir / "bbb_status.json"
    status_doc = _load_json(status_path) or {}
    status = status_doc.get("ball_by_ball_status") or "not_checked"
    primary = status_doc.get("primary_source")

    cricsheet = _load_json(commentary_dir / "deliveries_cricsheet.json")
    if cricsheet and (cricsheet.get("parse") or {}).get("ball_by_ball_status") == "complete":
        deliveries = (cricsheet.get("parse") or {}).get("deliveries") or []
        return "complete", deliveries, "Cricsheet"

    espn = _load_json(commentary_dir / "commentary_espn.json")
    if espn and (espn.get("deliveries") or []):
        return "partial", espn.get("deliveries") or [], "ESPNcricinfo"

    if status in {"complete", "partial", "unavailable"}:
        return status, [], primary
    return "not_checked", [], primary


def normalize_match(
    *,
    match_id: str,
    tournament_id: str | None = None,
    manifest: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = get_project_root()
    scorecard_path = root / "data" / "raw" / "scorecards" / match_id / "scorecard.json"
    out_dir = ensure_dir(root / "data" / "processed" / "matches")
    out_path = out_dir / f"{match_id}.json"

    result: dict[str, Any] = {
        "match_id": match_id,
        "tournament_id": tournament_id,
        "status": "skipped",
        "processed_at": utc_now_iso(),
        "output_path": str(out_path),
        "error": None,
    }

    if out_path.exists() and not force:
        result["status"] = "already_processed"
        return result

    scorecard = _load_json(scorecard_path)
    if not scorecard:
        result["status"] = "missing_scorecard"
        result["error"] = f"No scorecard.json at {scorecard_path}"
        return result

    bbb_status, raw_deliveries, bbb_source = _bbb_status_and_deliveries(root, match_id)
    match = parse_match_from_scorecard(
        scorecard,
        manifest=manifest,
        ball_by_ball_status=bbb_status,
    )
    if not match:
        result["status"] = "failed"
        result["error"] = "Match parse returned empty"
        return result

    teams = [
        standardize_team_record(
            {**t, "source_name": scorecard.get("source_name") or "ESPNcricinfo"}
        )
        for t in (scorecard.get("teams") or [])
        if isinstance(t, dict)
    ]
    players = merge_player_records(
        [
            {**p, "source_name": scorecard.get("source_name") or "ESPNcricinfo"}
            for p in (scorecard.get("players") or [])
        ]
    )
    innings = parse_innings_from_scorecard(scorecard)
    batting = parse_batting_from_scorecard(scorecard)
    bowling = parse_bowling_from_scorecard(scorecard)
    fielding = parse_fielding_from_scorecard(scorecard)
    deliveries = clean_delivery_list(raw_deliveries)

    # Also write entity slices for warehouse loaders
    ensure_dir(root / "data" / "processed" / "innings").joinpath(f"{match_id}.json").write_text(
        json.dumps(innings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ensure_dir(root / "data" / "processed" / "deliveries").joinpath(f"{match_id}.json").write_text(
        json.dumps(
            {
                "match_id": match_id,
                "ball_by_ball_status": bbb_status,
                "source_name": bbb_source,
                "delivery_count": len(deliveries),
                "deliveries": deliveries,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ensure_dir(root / "data" / "processed" / "players").joinpath(f"{match_id}.json").write_text(
        json.dumps(players, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    bundle = {
        "match_id": match_id,
        "tournament_id": match.get("tournament_id") or tournament_id,
        "normalized_at": result["processed_at"],
        "scorecard_parse_status": scorecard.get("parse_status"),
        "scorecard_status": scorecard.get("scorecard_status"),
        "ball_by_ball_status": bbb_status,
        "ball_by_ball_source": bbb_source,
        "match": match,
        "teams": teams,
        "players": players,
        "innings": innings,
        "batting_scorecards": batting,
        "bowling_scorecards": bowling,
        "fielding_scorecards": fielding,
        "delivery_count": len(deliveries),
        "awards": scorecard.get("awards") or [],
        "warnings": list(scorecard.get("warnings") or []),
    }
    out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    result["status"] = "ok"
    result["counts"] = {
        "teams": len(teams),
        "players": len(players),
        "innings": len(innings),
        "batting": len(batting),
        "bowling": len(bowling),
        "fielding": len(fielding),
        "deliveries": len(deliveries),
    }
    return result


def normalize_collected(
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    rows = load_match_manifest()
    if tournament_id:
        rows = [r for r in rows if r.get("tournament_id") == tournament_id]
    if match_ids:
        wanted = set(match_ids)
        rows = [r for r in rows if r.get("match_id") in wanted]
    # Only attempt matches that have a collected scorecard unless explicitly listed
    root = get_project_root()
    if not match_ids:
        rows = [
            r
            for r in rows
            if (
                root / "data" / "raw" / "scorecards" / (r.get("match_id") or "") / "scorecard.json"
            ).exists()
        ]
    if limit is not None:
        rows = rows[: max(0, limit)]

    started = utc_now_iso()
    results: list[dict[str, Any]] = []
    team_registry: dict[str, dict[str, Any]] = {}

    for row in rows:
        mid = row.get("match_id") or ""
        item = normalize_match(
            match_id=mid,
            tournament_id=row.get("tournament_id"),
            manifest=row,
            force=force,
        )
        results.append(item)
        if item.get("status") == "ok":
            bundle = _load_json(Path(item["output_path"])) or {}
            for team in bundle.get("teams") or []:
                tid = team.get("team_id")
                if tid:
                    team_registry[tid] = team

    teams_path = ensure_dir(root / "data" / "processed" / "teams") / "teams.json"
    existing = _load_json(teams_path) or {}
    if isinstance(existing, dict) and "teams" in existing:
        for team in existing.get("teams") or []:
            tid = (team or {}).get("team_id")
            if tid and tid not in team_registry:
                team_registry[tid] = team
    teams_path.write_text(
        json.dumps(
            {
                "updated_at": utc_now_iso(),
                "team_count": len(team_registry),
                "teams": sorted(team_registry.values(), key=lambda t: t.get("team_name") or ""),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "already_processed": sum(1 for r in results if r.get("status") == "already_processed"),
        "missing_scorecard": sum(1 for r in results if r.get("status") == "missing_scorecard"),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
    }
    report = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "tournament_id": tournament_id,
        "summary": summary,
        "results": results,
        "teams_path": str(teams_path),
    }
    report_path = ensure_dir(root / "data" / "processed") / "normalize_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    report["report_path"] = str(report_path)
    _update_collection_status(results)
    return report


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
                if row.get("entity_type") == "normalized" and row.get("entity_id") in touched:
                    continue
                existing.append(row)
    now = utc_now_iso()
    for row in results:
        existing.append(
            {
                "entity_type": "normalized",
                "entity_id": row.get("match_id") or "",
                "tournament_id": row.get("tournament_id") or "",
                "status": row.get("status") or "",
                "source_url": row.get("output_path") or "",
                "attempted_at": row.get("processed_at") or now,
                "completed_at": row.get("processed_at") or now,
                "error_message": row.get("error") or "",
                "notes": json.dumps(row.get("counts") or {}, ensure_ascii=False),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)
