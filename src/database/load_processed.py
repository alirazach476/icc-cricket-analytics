"""Load normalized match bundles from data/processed into PostgreSQL (Stage 10)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.collectors.scorecard_collector import load_match_manifest
from src.database.connection import session_scope
from src.database.repository import (
    finish_collection_run,
    parse_optional_date,
    parse_optional_datetime,
    start_collection_run,
    upsert_batting_scorecard,
    upsert_bowling_scorecard,
    upsert_delivery,
    upsert_fielding_scorecard,
    upsert_innings,
    upsert_match,
    upsert_match_team,
    upsert_player,
    upsert_team,
)
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")


def resolve_player_id(raw: str | None, *, default_source: str = "Cricsheet") -> tuple[str | None, dict[str, Any] | None]:
    """Return (player_id, optional stub player payload). Never invents ESPN merges."""
    if not raw:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    if text.startswith("espn_") or text.startswith("cricsheet_"):
        return text, None
    # Bare Cricsheet / name identity
    pid = f"cricsheet_{_slug(text)}"
    return pid, {
        "player_id": pid,
        "full_name": text,
        "source_name": default_source,
        "source_player_id": text,
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON %s: %s", path, exc)
        return None


def _source_id_map(session: Session) -> dict[str, int]:
    from sqlalchemy import select

    from src.database.models import Source

    return {s.name: s.source_id for s in session.scalars(select(Source)).all()}


def load_match_bundle(
    session: Session,
    bundle: dict[str, Any],
    *,
    deliveries_doc: dict[str, Any] | None = None,
    source_ids: dict[str, int] | None = None,
) -> dict[str, int]:
    """Upsert one normalized match into the warehouse. Returns entity counts."""
    source_ids = source_ids or {}
    match_id = bundle["match_id"]
    match = bundle.get("match") or {}
    counts = {
        "teams": 0,
        "players": 0,
        "matches": 0,
        "match_teams": 0,
        "innings": 0,
        "batting": 0,
        "bowling": 0,
        "fielding": 0,
        "deliveries": 0,
    }

    espn_source = source_ids.get("ESPNcricinfo")
    cricsheet_source = source_ids.get("Cricsheet")

    # Teams (scorecard list + any match/innings FK refs)
    known_teams: dict[str, dict[str, Any]] = {}
    for team in bundle.get("teams") or []:
        tid = team.get("team_id")
        if not tid:
            continue
        known_teams[tid] = {
            "team_id": tid,
            "team_name": team.get("team_name") or tid,
            "short_name": team.get("short_name"),
            "source_team_id": team.get("source_team_id"),
            "source_id": espn_source,
            "source_url": match.get("source_url"),
            "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
        }
    for tid, name in (
        (match.get("team1_id"), match.get("team1_name")),
        (match.get("team2_id"), match.get("team2_name")),
        (match.get("toss_winner_id"), None),
        (match.get("winner_id"), None),
    ):
        if tid and tid not in known_teams:
            known_teams[tid] = {
                "team_id": tid,
                "team_name": name or tid,
                "short_name": None,
                "source_team_id": str(tid).replace("espn_", "") if str(tid).startswith("espn_") else None,
                "source_id": espn_source,
                "source_url": match.get("source_url"),
                "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
            }
    for inn in bundle.get("innings") or []:
        for key in ("batting_team_id", "bowling_team_id"):
            tid = inn.get(key)
            if tid and tid not in known_teams:
                known_teams[tid] = {
                    "team_id": tid,
                    "team_name": tid,
                    "short_name": None,
                    "source_team_id": str(tid).replace("espn_", "") if str(tid).startswith("espn_") else None,
                    "source_id": espn_source,
                    "source_url": match.get("source_url"),
                    "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
                }
    for payload in known_teams.values():
        upsert_team(session, payload)
        counts["teams"] += 1

    # Players from scorecard + fielding + awards + deliveries
    player_payloads: dict[str, dict[str, Any]] = {}
    for player in bundle.get("players") or []:
        pid = player.get("player_id")
        if not pid:
            continue
        player_payloads[pid] = {
            "player_id": pid,
            "full_name": player.get("full_name") or player.get("batting_name") or pid,
            "source_name": player.get("source_name") or "ESPNcricinfo",
            "source_player_id": player.get("source_player_id"),
            "batting_style": player.get("batting_style"),
            "bowling_style": player.get("bowling_style"),
            "date_of_birth": parse_optional_date(player.get("date_of_birth")),
            "source_id": espn_source if (player.get("source_name") or "ESPNcricinfo") == "ESPNcricinfo" else cricsheet_source,
            "source_url": match.get("source_url"),
            "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
        }

    for row in bundle.get("fielding_scorecards") or []:
        pid = row.get("player_id")
        if pid and pid not in player_payloads:
            player_payloads[pid] = {
                "player_id": pid,
                "full_name": row.get("player_name") or pid,
                "source_name": "ESPNcricinfo",
                "source_player_id": pid.replace("espn_", "") if str(pid).startswith("espn_") else None,
                "source_id": espn_source,
            }

    for award in bundle.get("awards") or []:
        pid = award.get("player_id")
        if pid and pid not in player_payloads:
            player_payloads[pid] = {
                "player_id": pid,
                "full_name": award.get("player_name") or pid,
                "source_name": "ESPNcricinfo",
                "source_player_id": pid.replace("espn_", "") if str(pid).startswith("espn_") else None,
                "source_id": espn_source,
            }

    deliveries = list((deliveries_doc or {}).get("deliveries") or [])
    for d in deliveries:
        for field in ("batter_id", "non_striker_id", "bowler_id", "dismissed_player_id", "fielder_id"):
            resolved, stub = resolve_player_id(d.get(field))
            if stub and stub["player_id"] not in player_payloads:
                stub["source_id"] = cricsheet_source
                player_payloads[stub["player_id"]] = stub
            if resolved:
                d[field] = resolved

    for payload in player_payloads.values():
        upsert_player(session, payload)
        counts["players"] += 1

    # Match
    potm = match.get("player_of_match_id")
    if potm and potm not in player_payloads:
        # Avoid FK failure — null unknown potm rather than fabricate
        potm = None

    upsert_match(
        session,
        {
            "match_id": match_id,
            "tournament_id": match.get("tournament_id") or bundle.get("tournament_id"),
            "source_match_id": match.get("source_match_id") or match_id,
            "match_number": match.get("match_number"),
            "match_stage": match.get("match_stage"),
            "match_type": match.get("match_type"),
            "match_date": parse_optional_date(match.get("match_date")),
            "start_time": match.get("start_time"),
            "venue": match.get("venue"),
            "city": match.get("city"),
            "team1_id": match.get("team1_id"),
            "team2_id": match.get("team2_id"),
            "toss_winner_id": match.get("toss_winner_id"),
            "toss_decision": match.get("toss_decision"),
            "winner_id": match.get("winner_id"),
            "result_type": match.get("result_type"),
            "result_margin": match.get("result_margin"),
            "player_of_match_id": potm,
            "umpires": match.get("umpires"),
            "match_referee": match.get("match_referee"),
            "scorecard_url": match.get("scorecard_url"),
            "commentary_url": match.get("commentary_url"),
            "ball_by_ball_status": bundle.get("ball_by_ball_status")
            or match.get("ball_by_ball_status")
            or "not_checked",
            "scorecard_status": bundle.get("scorecard_status")
            or match.get("scorecard_status")
            or "not_checked",
            "match_status": match.get("match_status"),
            "source_id": espn_source,
            "source_url": match.get("source_url"),
            "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
        },
    )
    counts["matches"] += 1

    for idx, tid in enumerate((match.get("team1_id"), match.get("team2_id"))):
        if not tid:
            continue
        upsert_match_team(
            session,
            {
                "match_id": match_id,
                "team_id": tid,
                "is_home": idx == 0,
                "batting_order": idx + 1,
            },
        )
        counts["match_teams"] += 1

    innings_by_number: dict[int, dict[str, Any]] = {}
    for inn in bundle.get("innings") or []:
        innings_by_number[int(inn["innings_number"])] = inn
        upsert_innings(
            session,
            {
                "innings_id": inn["innings_id"],
                "match_id": match_id,
                "innings_number": int(inn["innings_number"]),
                "innings_type": inn.get("innings_type") or "standard",
                "batting_team_id": inn.get("batting_team_id"),
                "bowling_team_id": inn.get("bowling_team_id"),
                "total_runs": inn.get("total_runs"),
                "wickets": inn.get("wickets"),
                "overs": float(inn["overs"]) if inn.get("overs") is not None else None,
                "extras": inn.get("extras"),
                "declared": bool(inn.get("declared")),
                "is_super_over": bool(inn.get("is_super_over")),
                "target": inn.get("target") or None,
                "source_id": espn_source,
                "source_url": match.get("source_url"),
                "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
            },
        )
        counts["innings"] += 1

    # Cricsheet may include super-over innings absent from ESPN scorecard — create stubs
    for d in deliveries:
        inn_no = d.get("innings_number")
        if inn_no is None:
            continue
        inn_no = int(inn_no)
        if inn_no in innings_by_number:
            continue
        stub = {
            "innings_id": f"{match_id}_{inn_no}",
            "match_id": match_id,
            "innings_number": inn_no,
            "innings_type": d.get("innings_type") or ("super_over" if inn_no > 2 else "standard"),
            "batting_team_id": None,
            "bowling_team_id": None,
            "total_runs": None,
            "wickets": None,
            "overs": None,
            "extras": None,
            "declared": False,
            "is_super_over": bool((d.get("innings_type") == "super_over") or inn_no > 2),
            "target": None,
            "source_id": cricsheet_source,
            "source_url": d.get("source_url"),
            "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
        }
        innings_by_number[inn_no] = stub
        upsert_innings(session, stub)
        counts["innings"] += 1
        d["innings_id"] = stub["innings_id"]

    for row in bundle.get("batting_scorecards") or []:
        upsert_batting_scorecard(
            session,
            {
                "match_id": match_id,
                "innings_id": row.get("innings_id"),
                "innings_number": int(row["innings_number"]),
                "player_id": row["player_id"],
                "player_name": row.get("player_name"),
                "team_id": row.get("team_id"),
                "batting_position": row.get("batting_position"),
                "runs": row.get("runs"),
                "balls_faced": row.get("balls_faced"),
                "fours": row.get("fours"),
                "sixes": row.get("sixes"),
                "strike_rate": float(row["strike_rate"]) if row.get("strike_rate") is not None else None,
                "dismissal": row.get("dismissal"),
                "dismissal_type": row.get("dismissal_type"),
                "dismissed_by": row.get("dismissed_by"),
                "fielder": row.get("fielder"),
                "source_id": espn_source,
                "source_url": match.get("source_url"),
                "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
            },
        )
        counts["batting"] += 1

    for row in bundle.get("bowling_scorecards") or []:
        upsert_bowling_scorecard(
            session,
            {
                "match_id": match_id,
                "innings_id": row.get("innings_id"),
                "innings_number": int(row["innings_number"]),
                "player_id": row["player_id"],
                "player_name": row.get("player_name"),
                "team_id": row.get("team_id"),
                "overs": float(row["overs"]) if row.get("overs") is not None else None,
                "maidens": row.get("maidens"),
                "runs_conceded": row.get("runs_conceded"),
                "wickets": row.get("wickets"),
                "economy": float(row["economy"]) if row.get("economy") is not None else None,
                "dots": row.get("dots"),
                "wides": row.get("wides"),
                "no_balls": row.get("no_balls"),
                "source_id": espn_source,
                "source_url": match.get("source_url"),
                "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
            },
        )
        counts["bowling"] += 1

    for row in bundle.get("fielding_scorecards") or []:
        upsert_fielding_scorecard(
            session,
            {
                "match_id": match_id,
                "player_id": row["player_id"],
                "player_name": row.get("player_name"),
                "team_id": row.get("team_id"),
                "catches": int(row.get("catches") or 0),
                "run_outs": int(row.get("run_outs") or 0),
                "stumpings": int(row.get("stumpings") or 0),
                "source_id": espn_source,
                "source_url": match.get("source_url"),
                "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
            },
        )
        counts["fielding"] += 1

    bbb_source = (deliveries_doc or {}).get("source_name") or bundle.get("ball_by_ball_source")
    delivery_source_id = cricsheet_source if bbb_source == "Cricsheet" else espn_source
    for d in deliveries:
        # Drop cleaner warnings field — not a DB column
        upsert_delivery(
            session,
            {
                "delivery_id": d["delivery_id"],
                "match_id": match_id,
                "innings_id": d.get("innings_id") or f"{match_id}_{d['innings_number']}",
                "innings_number": int(d["innings_number"]),
                "innings_type": d.get("innings_type"),
                "over_number": d.get("over_number"),
                "ball_number": d.get("ball_number"),
                "delivery_sequence": int(d["delivery_sequence"]),
                "legal_ball_number": d.get("legal_ball_number"),
                "batter_id": d.get("batter_id"),
                "non_striker_id": d.get("non_striker_id"),
                "bowler_id": d.get("bowler_id"),
                "batter_runs": int(d.get("batter_runs") or 0),
                "extra_runs": int(d.get("extra_runs") or 0),
                "total_runs": int(d.get("total_runs") or 0),
                "extras_type": d.get("extras_type"),
                "is_wide": bool(d.get("is_wide")),
                "is_no_ball": bool(d.get("is_no_ball")),
                "is_bye": bool(d.get("is_bye")),
                "is_leg_bye": bool(d.get("is_leg_bye")),
                "is_penalty": bool(d.get("is_penalty")),
                "is_wicket": bool(d.get("is_wicket")),
                "dismissal_type": d.get("dismissal_type"),
                "dismissed_player_id": d.get("dismissed_player_id"),
                "fielder_id": d.get("fielder_id"),
                "commentary_text": d.get("commentary_text"),
                "source_id": delivery_source_id,
                "source_url": d.get("source_url"),
                "collected_at": parse_optional_datetime(bundle.get("normalized_at")),
            },
        )
        counts["deliveries"] += 1

    session.flush()
    return counts


def load_processed(
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = get_project_root()
    rows = load_match_manifest()
    if tournament_id:
        rows = [r for r in rows if r.get("tournament_id") == tournament_id]
    if match_ids:
        wanted = set(match_ids)
        rows = [r for r in rows if r.get("match_id") in wanted]

    candidates: list[str] = []
    for row in rows:
        mid = row.get("match_id") or ""
        if (root / "data" / "processed" / "matches" / f"{mid}.json").exists():
            candidates.append(mid)
    if not tournament_id and not match_ids:
        candidates = sorted(p.stem for p in (root / "data" / "processed" / "matches").glob("*.json"))

    # dedupe
    seen: set[str] = set()
    ordered = []
    for mid in candidates:
        if mid not in seen:
            seen.add(mid)
            ordered.append(mid)
    if limit is not None:
        ordered = ordered[: max(0, limit)]

    started = utc_now_iso()
    results: list[dict[str, Any]] = []

    if dry_run:
        return {
            "started_at": started,
            "finished_at": utc_now_iso(),
            "dry_run": True,
            "targeted": len(ordered),
            "results": [{"match_id": m, "status": "dry_run"} for m in ordered],
            "summary": {"dry_run": len(ordered)},
        }

    succeeded = 0
    failed = 0
    run_id: int | None = None

    with session_scope() as session:
        run = start_collection_run(
            session,
            pipeline_stage="db_load",
            tournament_id=tournament_id,
            dry_run=False,
        )
        run_id = run.collection_run_id

    for mid in ordered:
        try:
            with session_scope() as session:
                source_ids = _source_id_map(session)
                bundle = _load_json(root / "data" / "processed" / "matches" / f"{mid}.json")
                if not bundle:
                    results.append({"match_id": mid, "status": "missing", "error": "no bundle"})
                    failed += 1
                    continue
                deliveries_doc = _load_json(root / "data" / "processed" / "deliveries" / f"{mid}.json")
                counts = load_match_bundle(
                    session,
                    bundle,
                    deliveries_doc=deliveries_doc,
                    source_ids=source_ids,
                )
                results.append({"match_id": mid, "status": "ok", "counts": counts})
                succeeded += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed loading match %s", mid)
            results.append({"match_id": mid, "status": "failed", "error": str(exc)})
            failed += 1

    with session_scope() as session:
        from src.database.models import CollectionRun

        run = session.get(CollectionRun, run_id)
        if run is not None:
            finish_collection_run(
                session,
                run,
                status="completed" if failed == 0 else "completed_with_errors",
                attempted=len(ordered),
                succeeded=succeeded,
                failed=failed,
            )

    summary = {
        "targeted": len(ordered),
        "ok": succeeded,
        "failed": failed,
        "missing": sum(1 for r in results if r.get("status") == "missing"),
    }
    report = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "dry_run": False,
        "tournament_id": tournament_id,
        "collection_run_id": run_id,
        "summary": summary,
        "results": results,
    }
    report_path = ensure_dir(root / "data" / "processed" / "validation") / (
        f"db_load_report_{tournament_id or 'all'}.json"
    )
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
