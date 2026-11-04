"""Parse ESPNcricinfo points-table and squad pages (embedded __NEXT_DATA__ JSON)."""

from __future__ import annotations

import json
import re
from typing import Any

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_SQUAD_LINK = re.compile(r'href="(/series/[^"]+/[a-z0-9-]+-squad-\d+/series-squads)"', re.I)


def extract_next_data(html: str) -> dict[str, Any] | None:
    match = _NEXT_DATA.search(html or "")
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _find_key(obj: Any, key: str, predicate=None) -> Any:
    """Depth-first search for the first dict value stored under ``key``."""
    if isinstance(obj, dict):
        if key in obj and (predicate is None or predicate(obj[key])):
            return obj[key]
        for value in obj.values():
            found = _find_key(value, key, predicate)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_key(value, key, predicate)
            if found is not None:
                return found
    return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_standings_html(html: str, *, tournament_id: str, source_url: str) -> dict[str, Any]:
    """Return ``{"rows": [...], "parse_status": ..., "warnings": [...]}``."""
    result: dict[str, Any] = {
        "tournament_id": tournament_id,
        "source_name": "ESPNcricinfo",
        "source_url": source_url,
        "parse_status": "failed",
        "warnings": [],
        "rows": [],
    }
    data = extract_next_data(html)
    if not data:
        result["warnings"].append("No __NEXT_DATA__ found")
        return result
    standings = _find_key(
        data, "standings", lambda v: isinstance(v, dict) and isinstance(v.get("groups"), list)
    )
    if not standings:
        result["warnings"].append("No standings.groups in page data")
        return result

    for group in standings["groups"]:
        group_name = (group.get("name") or "Overall").strip()
        qualify_count = _to_int(group.get("teamsToQualifyCount")) or 0
        for entry in group.get("teamStats") or []:
            info = entry.get("teamInfo") or {}
            object_id = info.get("objectId") or info.get("id")
            if object_id is None:
                result["warnings"].append(f"Row without team id in {group_name}")
                continue
            rank = _to_int(entry.get("rank"))
            result["rows"].append(
                {
                    "tournament_id": tournament_id,
                    "group_name": group_name,
                    "team_id": f"espn_{object_id}",
                    "team_name": info.get("longName") or info.get("name"),
                    "short_name": info.get("abbreviation"),
                    "source_team_id": str(object_id),
                    "position": rank,
                    "matches_played": _to_int(entry.get("matchesPlayed")),
                    "wins": _to_int(entry.get("matchesWon")),
                    "losses": _to_int(entry.get("matchesLost")),
                    "ties": _to_int(entry.get("matchesTied")),
                    "no_results": _to_int(entry.get("matchesNoResult")),
                    "points": _to_float(entry.get("points")),
                    "net_run_rate": _to_float(entry.get("nrr")),
                    "runs_for": entry.get("for"),
                    "runs_against": entry.get("against"),
                    "group_match_ids": [str(m) for m in (entry.get("allMatchObjectIds") or [])],
                    "qualified": (rank <= qualify_count) if (qualify_count and rank) else None,
                }
            )
    result["parse_status"] = "ok" if result["rows"] else "empty"
    if not result["rows"]:
        result["warnings"].append("Standings present but no team rows")
    return result


def derive_qualification(
    rows: list[dict[str, Any]], matches: list[dict[str, str]]
) -> dict[str, int]:
    """Fill ``qualified`` using only Cricinfo data: a team qualified out of a group if it
    plays a match dated after that group's last match (a later group or a knockout).

    ``matches`` are manifest rows (match_id, match_date, team1_name, team2_name).
    Groups for which Cricinfo lists no matches are left as ``None`` (not guessed).
    Rows are modified in place; returns counts.
    """
    by_id = {m["match_id"]: m for m in matches}
    team_dates: dict[str, list[str]] = {}
    for m in matches:
        if not m.get("match_date"):
            continue
        for key in ("team1_name", "team2_name"):
            if m.get(key):
                team_dates.setdefault(m[key], []).append(m["match_date"])

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["group_name"], []).append(row)

    counts = {"true": 0, "false": 0, "unknown": 0}
    for group_rows in groups.values():
        dates = [
            by_id[mid]["match_date"]
            for row in group_rows
            for mid in row.get("group_match_ids") or []
            if mid in by_id and by_id[mid].get("match_date")
        ]
        if not dates:
            counts["unknown"] += len(group_rows)  # leave qualified as None
            continue
        last = max(dates)
        for row in group_rows:
            row["qualified"] = any(d > last for d in team_dates.get(row["team_name"], []))
            counts["true" if row["qualified"] else "false"] += 1
    return counts


def parse_squad_index_html(html: str) -> list[str]:
    """Return relative links to each team's squad page, in page order, de-duplicated."""
    seen: dict[str, None] = {}
    for link in _SQUAD_LINK.findall(html or ""):
        seen.setdefault(link, None)
    return list(seen)


def parse_squad_html(
    html: str, *, tournament_id: str, source_url: str
) -> dict[str, Any]:
    """Parse one team's squad page into a team + player list."""
    result: dict[str, Any] = {
        "tournament_id": tournament_id,
        "source_name": "ESPNcricinfo",
        "source_url": source_url,
        "parse_status": "failed",
        "warnings": [],
        "team_id": None,
        "team_name": None,
        "announced_at": None,
        "players": [],
    }
    data = extract_next_data(html)
    if not data:
        result["warnings"].append("No __NEXT_DATA__ found")
        return result

    def _has_players(v: Any) -> bool:
        return isinstance(v, list) and bool(v) and isinstance(v[0], dict) and "player" in v[0]

    holder = None

    def _walk(obj: Any) -> None:
        nonlocal holder
        if holder is not None:
            return
        if isinstance(obj, dict):
            if _has_players(obj.get("players")) and isinstance(obj.get("squad"), dict):
                holder = obj
                return
            for value in obj.values():
                _walk(value)
        elif isinstance(obj, list):
            for value in obj:
                _walk(value)

    _walk(data)
    if holder is None:
        result["warnings"].append("No squad players in page data")
        return result

    squad = holder["squad"]
    team_object_id = squad.get("teamObjectId") or squad.get("teamId")
    result["team_id"] = f"espn_{team_object_id}" if team_object_id is not None else None
    result["team_name"] = squad.get("teamName")
    result["announced_at"] = squad.get("announcedAt")

    for entry in holder["players"]:
        player = entry.get("player") or {}
        object_id = player.get("objectId") or player.get("id")
        if object_id is None:
            result["warnings"].append("Player without id skipped")
            continue
        role_code = entry.get("playerRoleType")
        roles = [r for r in (player.get("playingRoles") or []) if isinstance(r, str)]
        dob = player.get("dateOfBirth") or {}
        result["players"].append(
            {
                "player_id": f"espn_{object_id}",
                "source_player_id": str(object_id),
                "full_name": player.get("longName") or player.get("name"),
                "batting_name": player.get("battingName"),
                "role_code": role_code,
                "is_captain": role_code in {"C", "CWK"},
                "is_wicketkeeper": role_code in {"WK", "CWK"},
                "playing_roles": roles,
                "batting_style": ", ".join(player.get("longBattingStyles") or []) or None,
                "bowling_style": ", ".join(player.get("longBowlingStyles") or []) or None,
                "date_of_birth": _dob_iso(dob),
                "is_overseas": bool(entry.get("isOverseas")),
                "is_withdrawn": bool(entry.get("isWithdrawn")),
                "note": entry.get("note"),
            }
        )
    result["parse_status"] = "ok" if result["players"] else "empty"
    return result


def _dob_iso(dob: Any) -> str | None:
    if not isinstance(dob, dict):
        return None
    year, month, date = dob.get("year"), dob.get("month"), dob.get("date")
    if year and month and date:
        return f"{int(year):04d}-{int(month):02d}-{int(date):02d}"
    return None
