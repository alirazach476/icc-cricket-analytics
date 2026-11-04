# ruff: noqa: E501
"""ESPNcricinfo scorecards, schedules, standings and squads -> silver rows (Champions Trophy)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.parsers.match_list_parser import map_match_stage
from src.transformations.identity import RosterPlayer, norm
from src.transformations.silver import parse_result

ROOT = Path(__file__).resolve().parents[2]
PARSED = ROOT / "data" / "competitions" / "espn"
KNOCKOUT = {"Final", "Semifinal", "Quarterfinal", "Third place"}


def load_edition(tid: str) -> dict[str, Any] | None:
    d = PARSED / tid
    if not (d / "schedule.json").exists():
        return None
    sched = json.loads((d / "schedule.json").read_text(encoding="utf-8"))["matches"]
    cards = {}
    for f in (d / "scorecards").glob("*.json"):
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("parse_status") in ("ok", "partial"):
            cards[str(c["match_id"])] = c
    squads = (
        json.loads((d / "squads.json").read_text(encoding="utf-8")).get("squads", [])
        if (d / "squads.json").exists()
        else []
    )
    standings = (
        json.loads((d / "standings.json").read_text(encoding="utf-8")).get("rows", [])
        if (d / "standings.json").exists()
        else []
    )
    return {
        "schedule": {str(m["match_id"]): m for m in sched},
        "cards": cards,
        "squads": squads,
        "standings": standings,
    }


def card_roster(card: dict) -> list[RosterPlayer]:
    """Everyone named on one ESPN scorecard, with the team they played for."""
    team_of: dict[str, str] = {}
    for key in ("batting_scorecards", "bowling_scorecards", "fielding_scorecards"):
        for r in card.get(key, []):
            team_of.setdefault(r["player_id"], r.get("team_id"))
    out = []
    for p in card.get("players", []):
        out.append(
            RosterPlayer(
                p["player_id"],
                p.get("player_name") or "",
                p.get("batting_name") or p.get("player_name") or "",
                team_of.get(p["player_id"]),
            )
        )
    return out


def _balls(overs: float | None) -> int | None:
    if overs is None or overs != overs:
        return None
    whole = int(overs)
    return whole * 6 + int(round((overs - whole) * 10))


def espn_match(
    rec: dict, card: dict | None, ident: Any, tournament_id: str, group_of: dict[str, str]
) -> dict[str, Any]:
    """Silver rows for a match that only ESPNcricinfo has (no ball-by-ball)."""
    mid = str(rec["match_id"])
    res = parse_result(rec.get("result_margin"), rec.get("result_type"))
    stage = rec.get("match_stage") or map_match_stage(rec.get("match_type"), None)
    stage = {
        "Semi-Final": "Semifinal",
        "Semi Final": "Semifinal",
        "Quarter-Final": "Quarterfinal",
    }.get(stage, stage)
    title = rec.get("match_type") or ""
    result_type = (rec.get("result_type") or "RESULT").upper()
    winner_id = rec.get("winner_id")
    has_winner = bool(winner_id) and result_type == "RESULT" and not res["is_tie"]
    tie_winner = res.get("tie_break_winner_name")
    if res["is_tie"] and tie_winner:
        winner_id = next(
            (
                t
                for t in (rec["team1_id"], rec["team2_id"])
                if norm(ident.team_name(t)) == norm(tie_winner)
            ),
            winner_id,
        )
        has_winner = True
    match = {
        "match_id": mid,
        "tournament_id": tournament_id,
        "match_number": rec.get("match_number"),
        "match_date": pd.to_datetime(rec["match_date"]).date(),
        "start_time": pd.to_datetime(rec.get("start_time"), utc=True, errors="coerce"),
        "venue": rec.get("venue"),
        "city": rec.get("city"),
        "team1_id": rec["team1_id"],
        "team2_id": rec["team2_id"],
        "team1_name": rec["team1_name"],
        "team2_name": rec["team2_name"],
        "toss_winner_id": rec.get("toss_winner_id"),
        "toss_decision": rec.get("toss_decision"),
        "winner_id": winner_id if has_winner else None,
        "result_type": result_type,
        "result_margin": rec.get("result_margin"),
        "player_of_match_id": next(
            (
                a["player_id"]
                for a in (card or {}).get("awards", [])
                if a.get("award_type") == "PLAYER_OF_MATCH"
            ),
            None,
        ),
        "scorecard_url": rec.get("scorecard_url"),
        "commentary_url": rec.get("commentary_url"),
        "ball_by_ball_status": "unavailable",
        "ball_by_ball_source": None,
        "scorecard_status": "complete" if card and card.get("innings") else "missing",
        "source_url": rec.get("scorecard_url"),
        "winner_id_source": winner_id,
        "winner_id_corrected": False,
        "toss_winner_id_source": rec.get("toss_winner_id"),
        "toss_winner_id_corrected": False,
        "margin_type": res["margin_type"],
        "margin_value": None if pd.isna(res["margin_value"]) else float(res["margin_value"]),
        "balls_remaining": None
        if pd.isna(res["balls_remaining"])
        else float(res["balls_remaining"]),
        "is_tie": bool(res["is_tie"]),
        "tie_break_method": res["tie_break_method"],
        "tie_break_winner_name": tie_winner,
        "is_dls": bool(res["is_dls"]),
        "is_walkover": False,
        "result_winner_name": res["result_winner_name"],
        "winner_source": "result" if has_winner else None,
        "has_winner": has_winner,
        "match_type": title,
        "source_title": title,
        "group_name": group_of.get(mid),
        "match_stage_source": stage,
        "stage": stage,
        "is_knockout": stage in KNOCKOUT,
        "venue_clean": rec.get("venue"),
        "venue_name_canonical": rec.get("venue"),
        "venue_key": norm(rec.get("venue")) if rec.get("venue") else None,
    }
    inn, bat, bowl, field, xi = [], [], [], [], {}
    if card:
        for i in card.get("innings", []):
            balls = _balls(i.get("overs"))
            inn.append(
                {
                    "match_id": mid,
                    "innings_id": f"{mid}_{i['innings_number']}",
                    "innings_number": i["innings_number"],
                    "innings_type": i.get("innings_type") or "standard",
                    "batting_team_id": i["batting_team_id"],
                    "bowling_team_id": i["bowling_team_id"],
                    "total_runs": i["total_runs"],
                    "wickets": i["wickets"],
                    "overs": i.get("overs"),
                    "extras": i.get("extras"),
                    "byes": i.get("byes"),
                    "legbyes": i.get("legbyes"),
                    "wides": i.get("wides"),
                    "noballs": i.get("noballs"),
                    "penalties": i.get("penalties"),
                    "declared": False,
                    "is_super_over": bool(i.get("is_super_over")),
                    "target": i.get("target") or None,
                    "source_name": "ESPNcricinfo",
                    "source_url": rec.get("scorecard_url"),
                    "_source_file": f"data/competitions/espn/{tournament_id}/scorecards/{mid}.json",
                    "legal_balls": balls,
                    "derived_from_deliveries": False,
                    "overs_source": i.get("overs"),
                }
            )
        for b in card.get("batting_scorecards", []):
            did = b.get("batted_type") in ("yes", True) or b.get("runs") is not None
            bat.append(
                {
                    "batting_scorecard_id": f"{mid}_{b['innings_number']}_{b['player_id']}",
                    "match_id": mid,
                    "innings_id": f"{mid}_{b['innings_number']}",
                    "innings_number": b["innings_number"],
                    "player_id": b["player_id"],
                    "player_name": b["player_name"],
                    "team_id": b["team_id"],
                    "batting_position": b.get("batting_position"),
                    "did_bat": bool(did),
                    "runs": b.get("runs"),
                    "balls_faced": b.get("balls_faced"),
                    "fours": b.get("fours"),
                    "sixes": b.get("sixes"),
                    "strike_rate": b.get("strike_rate"),
                    "is_out": bool(b.get("is_out")),
                    "dismissal_type": b.get("dismissal_type"),
                    "dismissal": b.get("dismissal"),
                    "dismissed_by": b.get("dismissed_by"),
                    "fielder": b.get("fielder"),
                    "source_url": rec.get("scorecard_url"),
                }
            )
        for w in card.get("bowling_scorecards", []):
            bb = _balls(w.get("overs"))
            bowl.append(
                {
                    "bowling_scorecard_id": f"{mid}_{w['innings_number']}_{w['player_id']}",
                    "match_id": mid,
                    "innings_id": f"{mid}_{w['innings_number']}",
                    "innings_number": w["innings_number"],
                    "player_id": w["player_id"],
                    "player_name": w["player_name"],
                    "team_id": w["team_id"],
                    "overs": w.get("overs"),
                    "balls_bowled": bb,
                    "maidens": w.get("maidens"),
                    "runs_conceded": w.get("runs_conceded"),
                    "wickets": w.get("wickets"),
                    "economy": w.get("economy"),
                    "dots": w.get("dots"),
                    "wides": w.get("wides"),
                    "no_balls": w.get("no_balls"),
                    "source_url": rec.get("scorecard_url"),
                }
            )
        for f in card.get("fielding_scorecards", []):
            field.append(
                {
                    "match_id": mid,
                    "player_id": f["player_id"],
                    "player_name": f["player_name"],
                    "team_id": f["team_id"],
                    "catches": f.get("catches", 0),
                    "run_outs": f.get("run_outs", 0),
                    "stumpings": f.get("stumpings", 0),
                    "source_url": rec.get("scorecard_url"),
                }
            )
        for p in card_roster(card):
            xi.setdefault(p.team_id, []).append((p.full_name, p.player_id))
    pom = next(
        (
            (a["player_id"], a.get("player_name"))
            for a in (card or {}).get("awards", [])
            if a.get("award_type") == "PLAYER_OF_MATCH"
        ),
        None,
    )
    return {
        "match": match,
        "innings": inn,
        "deliveries": [],
        "batting": bat,
        "bowling": bowl,
        "fielding": field,
        "xi": xi,
        "pom": pom,
        "espn_only": True,
    }


def standings_rows(tid: str, rows: list[dict], matches: pd.DataFrame, batch: str) -> list[dict]:
    ko = matches[(matches["tournament_id"] == tid) & matches["is_knockout"]]
    in_ko = set(ko["team1_id"]) | set(ko["team2_id"])
    now = datetime.now(UTC).isoformat()
    out = []
    for r in rows:
        out.append(
            {
                "tournament_id": tid,
                "group_name": r["group_name"],
                "team_id": r["team_id"],
                "team_name": r["team_name"],
                "short_name": r.get("short_name"),
                "source_team_id": r.get("source_team_id"),
                "position": r["position"],
                "matches_played": r["matches_played"],
                "wins": r["wins"],
                "losses": r["losses"],
                "ties": (r["matches_played"] - r["wins"] - r["losses"])
                if tid.startswith("WTC")
                else r["ties"],
                "no_results": r["no_results"],
                "points": r["points"],
                "net_run_rate": r["net_run_rate"],
                "runs_for": r.get("runs_for"),
                "runs_against": r.get("runs_against"),
                "qualified": (r["team_id"] in in_ko) if len(ko) else None,
                "collected_at": now,
                "_source_file": f"data/competitions/espn/{tid}/standings.json",
                "_batch_id": batch,
                "_ingested_at": now,
            }
        )
    return out


def squad_rows(tid: str, squads: list[dict], batch: str) -> list[dict]:
    now = datetime.now(UTC).isoformat()
    out = []
    for s in squads:
        for p in s["players"]:
            out.append(
                {
                    "tournament_id": tid,
                    "team_id": s["team_id"],
                    "team_name": s["team_name"],
                    "announced_at": s.get("announced_at"),
                    "player_id": p["player_id"],
                    "source_player_id": p["source_player_id"],
                    "full_name": p["full_name"],
                    "batting_name": p["batting_name"],
                    "role_code": p["role_code"],
                    "is_captain": p["is_captain"],
                    "is_wicketkeeper": p["is_wicketkeeper"],
                    "playing_roles": json.dumps(p["playing_roles"]),
                    "batting_style": p["batting_style"],
                    "bowling_style": p["bowling_style"],
                    "date_of_birth": p["date_of_birth"],
                    "is_overseas": p["is_overseas"],
                    "is_withdrawn": p["is_withdrawn"],
                    "note": p["note"],
                    "collected_at": now,
                    "_source_file": f"data/competitions/espn/{tid}/squads.json",
                    "_batch_id": batch,
                    "_ingested_at": now,
                    "source": "espncricinfo",
                }
            )
    return out
