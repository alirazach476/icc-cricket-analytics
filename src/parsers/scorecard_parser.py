"""Parse ESPNcricinfo full-scorecard HTML into structured match scorecards."""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_json(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _player_ref(player: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(player, dict) or player.get("objectId") is None:
        return None
    return {
        "player_id": f"espn_{player['objectId']}",
        "source_player_id": str(player["objectId"]),
        "player_name": player.get("longName") or player.get("name"),
        "batting_name": player.get("battingName") or player.get("name"),
    }


def _team_ref(team: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(team, dict) or team.get("objectId") is None:
        return None
    return {
        "team_id": f"espn_{team['objectId']}",
        "source_team_id": str(team["objectId"]),
        "team_name": team.get("longName") or team.get("name"),
        "abbreviation": team.get("abbreviation"),
    }


def _parse_batting_row(
    row: dict[str, Any],
    *,
    match_id: str,
    innings_number: int,
    team: dict[str, Any] | None,
    position: int,
) -> dict[str, Any] | None:
    player = _player_ref(row.get("player"))
    if not player:
        return None
    dismissal_text = row.get("dismissalText") or {}
    bowler = _player_ref(row.get("dismissalBowler"))
    fielders = row.get("dismissalFielders") or []
    fielder_names = []
    for item in fielders:
        ref = _player_ref((item or {}).get("player"))
        if ref and ref.get("player_name"):
            fielder_names.append(ref["player_name"])

    return {
        "match_id": match_id,
        "innings_number": innings_number,
        "player_id": player["player_id"],
        "player_name": player["player_name"],
        "team_id": (team or {}).get("team_id"),
        "batting_position": position,
        "runs": row.get("runs"),
        "balls_faced": row.get("balls"),
        "fours": row.get("fours"),
        "sixes": row.get("sixes"),
        "strike_rate": row.get("strikerate"),
        "dismissal": dismissal_text.get("long") if isinstance(dismissal_text, dict) else None,
        "dismissal_type": dismissal_text.get("short") if isinstance(dismissal_text, dict) else None,
        "dismissed_by": (bowler or {}).get("player_name"),
        "fielder": ", ".join(fielder_names) if fielder_names else (
            dismissal_text.get("fielderText") if isinstance(dismissal_text, dict) else None
        ),
        "is_out": bool(row.get("isOut")),
        "batted_type": row.get("battedType"),
    }


def _parse_bowling_row(
    row: dict[str, Any],
    *,
    match_id: str,
    innings_number: int,
    bowling_team: dict[str, Any] | None,
) -> dict[str, Any] | None:
    player = _player_ref(row.get("player"))
    if not player:
        return None
    return {
        "match_id": match_id,
        "innings_number": innings_number,
        "player_id": player["player_id"],
        "player_name": player["player_name"],
        "team_id": (bowling_team or {}).get("team_id"),
        "overs": row.get("overs"),
        "maidens": row.get("maidens"),
        "runs_conceded": row.get("conceded"),
        "wickets": row.get("wickets"),
        "economy": row.get("economy"),
        "dots": row.get("dots"),
        "wides": row.get("wides"),
        "no_balls": row.get("noballs"),
    }


def _aggregate_fielding(batting_rows: list[dict[str, Any]], innings_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive fielding counts only from dismissal records present in the source."""
    stats: dict[str, dict[str, Any]] = {}

    def ensure(player: dict[str, Any], team_id: str | None) -> dict[str, Any]:
        pid = player["player_id"]
        if pid not in stats:
            stats[pid] = {
                "player_id": pid,
                "player_name": player["player_name"],
                "team_id": team_id,
                "catches": 0,
                "run_outs": 0,
                "stumpings": 0,
            }
        return stats[pid]

    for inn in innings_payloads:
        for row in inn.get("inningBatsmen") or []:
            dtype = ((row.get("dismissalText") or {}).get("short") or "").lower()
            fielders = row.get("dismissalFielders") or []
            for item in fielders:
                pref = _player_ref((item or {}).get("player"))
                if not pref:
                    continue
                # Fielding team is bowling side for this innings
                bowling_team = inn.get("_bowling_team_ref")
                entry = ensure(pref, (bowling_team or {}).get("team_id"))
                if "stump" in dtype:
                    entry["stumpings"] += 1
                elif "run out" in dtype:
                    entry["run_outs"] += 1
                elif "caught" in dtype or dtype == "c":
                    entry["catches"] += 1
    return list(stats.values())


def parse_scorecard_html(
    html: str,
    *,
    match_id: str,
    tournament_id: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Parse a full-scorecard page into structured scorecard data."""
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, Any] = {
        "match_id": match_id,
        "tournament_id": tournament_id,
        "source_url": source_url,
        "source_name": "ESPNcricinfo",
        "parse_status": "ok",
        "scorecard_status": "complete",
        "warnings": [],
        "match": None,
        "innings": [],
        "batting_scorecards": [],
        "bowling_scorecards": [],
        "fielding_scorecards": [],
        "awards": [],
        "players": [],
        "teams": [],
    }

    next_data = _safe_json(soup.find("script", id="__NEXT_DATA__").string if soup.find("script", id="__NEXT_DATA__") else None)
    if not isinstance(next_data, dict):
        result["parse_status"] = "failed"
        result["scorecard_status"] = "missing"
        result["warnings"].append("Missing __NEXT_DATA__")
        return result

    data = ((next_data.get("props") or {}).get("appPageProps") or {}).get("data")
    if not isinstance(data, dict):
        result["parse_status"] = "failed"
        result["scorecard_status"] = "missing"
        result["warnings"].append("Missing appPageProps.data")
        return result

    match = data.get("match") or {}
    content = data.get("content") or {}
    teams_raw = match.get("teams") or []
    team_refs = []
    for side in teams_raw:
        ref = _team_ref((side or {}).get("team"))
        if ref:
            team_refs.append(ref)
            result["teams"].append(ref)

    ground = match.get("ground") or {}
    town = ground.get("town") if isinstance(ground.get("town"), dict) else {}
    potm = None
    for award in content.get("matchPlayerAwards") or []:
        pref = _player_ref((award or {}).get("player"))
        if not pref:
            continue
        result["awards"].append(
            {
                "award_type": award.get("type"),
                "player_id": pref["player_id"],
                "player_name": pref["player_name"],
            }
        )
        if award.get("type") == "PLAYER_OF_MATCH":
            potm = pref["player_id"]

    result["match"] = {
        "match_id": match_id,
        "tournament_id": tournament_id,
        "source_match_id": str(match.get("objectId") or match_id),
        "match_date": str(match.get("startDate"))[:10] if match.get("startDate") else None,
        "start_time": match.get("startTime"),
        "venue": ground.get("name") or ground.get("longName"),
        "city": town.get("name") or ground.get("smallName"),
        "title": match.get("title"),
        "status": match.get("status"),
        "status_text": match.get("statusText"),
        "result_type": match.get("status"),
        "result_margin": match.get("statusText"),
        "is_cancelled": bool(match.get("isCancelled")),
        "is_super_over": bool(match.get("isSuperOver")),
        "toss_winner_id": f"espn_{match['tossWinnerTeamId']}" if match.get("tossWinnerTeamId") else None,
        "toss_decision": match.get("tossWinnerChoice"),
        "winner_id": f"espn_{match['winnerTeamId']}" if match.get("winnerTeamId") else None,
        "team1_id": team_refs[0]["team_id"] if len(team_refs) > 0 else None,
        "team2_id": team_refs[1]["team_id"] if len(team_refs) > 1 else None,
        "player_of_match_id": potm,
        "umpires": None,
        "match_referee": None,
        "source_url": source_url,
    }

    innings_list = list(content.get("innings") or [])
    # Preserve Super Over innings separately when present
    for so in content.get("superOverInnings") or []:
        if isinstance(so, dict):
            so = dict(so)
            so["_is_super_over"] = True
            innings_list.append(so)

    players: dict[str, dict[str, Any]] = {}
    batting_rows: list[dict[str, Any]] = []
    bowling_rows: list[dict[str, Any]] = []
    prepared_innings: list[dict[str, Any]] = []

    for inn in innings_list:
        if not isinstance(inn, dict):
            continue
        innings_number = inn.get("inningNumber")
        batting_team = _team_ref(inn.get("team"))
        # bowling team is the other side when two teams known
        bowling_team = None
        if batting_team and len(team_refs) == 2:
            bowling_team = next(
                (t for t in team_refs if t["team_id"] != batting_team["team_id"]),
                None,
            )
        inn["_bowling_team_ref"] = bowling_team
        prepared_innings.append(inn)

        innings_id = f"{match_id}_{innings_number}"
        result["innings"].append(
            {
                "innings_id": innings_id,
                "match_id": match_id,
                "innings_number": innings_number,
                "innings_type": "super_over" if inn.get("_is_super_over") else "standard",
                "batting_team_id": (batting_team or {}).get("team_id"),
                "bowling_team_id": (bowling_team or {}).get("team_id"),
                "total_runs": inn.get("runs"),
                "wickets": inn.get("wickets"),
                "overs": inn.get("overs"),
                "extras": inn.get("extras"),
                "byes": inn.get("byes"),
                "legbyes": inn.get("legbyes"),
                "wides": inn.get("wides"),
                "noballs": inn.get("noballs"),
                "penalties": inn.get("penalties"),
                "target": inn.get("target"),
                "is_super_over": bool(inn.get("_is_super_over")),
            }
        )

        pos = 0
        for row in inn.get("inningBatsmen") or []:
            # Keep only actual batting cards (skip yet-to-bat placeholders without battedType yes/no meaningful?)
            if row.get("battedType") in {None, "no"} and row.get("runs") is None and not row.get("isOut"):
                # yet to bat / did not bat placeholders — skip without fabricating
                if row.get("battedType") == "no":
                    continue
            pos += 1
            parsed = _parse_batting_row(
                row,
                match_id=match_id,
                innings_number=int(innings_number),
                team=batting_team,
                position=pos,
            )
            if parsed:
                batting_rows.append(parsed)
                pref = _player_ref(row.get("player"))
                if pref:
                    players[pref["player_id"]] = pref

        for row in inn.get("inningBowlers") or []:
            parsed = _parse_bowling_row(
                row,
                match_id=match_id,
                innings_number=int(innings_number),
                bowling_team=bowling_team,
            )
            if parsed:
                bowling_rows.append(parsed)
                pref = _player_ref(row.get("player"))
                if pref:
                    players[pref["player_id"]] = pref

    result["batting_scorecards"] = batting_rows
    result["bowling_scorecards"] = bowling_rows
    result["fielding_scorecards"] = [
        {**row, "match_id": match_id} for row in _aggregate_fielding(batting_rows, prepared_innings)
    ]
    result["players"] = list(players.values())

    if not result["innings"]:
        result["parse_status"] = "partial"
        result["scorecard_status"] = "partial"
        result["warnings"].append("No innings found in scorecard payload")
    elif not batting_rows and not bowling_rows:
        result["parse_status"] = "partial"
        result["scorecard_status"] = "partial"
        result["warnings"].append("Innings present but no batting/bowling rows")

    return result
