"""Load processed standings and squads JSON into the database.

Dialect-agnostic (select-then-update) so it works on PostgreSQL and SQLite.
Teams and players referenced by a squad/standing but not yet in the database are created.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Player, Source, Squad, Standing, Team, Tournament
from src.utils.config import get_project_root
from src.utils.logger import get_logger

logger = get_logger(__name__)

SOURCE_NAME = "ESPNcricinfo"


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _ensure_team(session: Session, team_id: str, name: str | None, short: str | None,
                 source_team_id: str | None, source_id: int | None) -> bool:
    if session.get(Team, team_id) is not None:
        return False
    existing = session.scalar(select(Team).where(Team.team_name == (name or team_id)))
    if existing is not None:
        return False  # name is unique; keep the existing id rather than duplicate
    session.add(
        Team(
            team_id=team_id,
            team_name=name or team_id,
            short_name=short,
            source_team_id=source_team_id,
            source_id=source_id,
        )
    )
    session.flush()
    return True


def _resolve_team_id(session: Session, team_id: str, name: str | None) -> str:
    """Prefer the id already stored for this team name (names are unique)."""
    if session.get(Team, team_id) is not None:
        return team_id
    existing = session.scalar(select(Team).where(Team.team_name == name)) if name else None
    return existing.team_id if existing is not None else team_id


def load_standings(session: Session, doc: dict[str, Any], source_id: int | None) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "teams_created": 0}
    tid = doc["tournament_id"]
    if session.get(Tournament, tid) is None:
        raise ValueError(f"Tournament {tid} not in database; load tournaments first")
    collected_at = _parse_dt(doc.get("collected_at"))
    for row in doc.get("rows") or []:
        if _ensure_team(session, row["team_id"], row.get("team_name"), row.get("short_name"),
                        row.get("source_team_id"), source_id):
            counts["teams_created"] += 1
        team_id = _resolve_team_id(session, row["team_id"], row.get("team_name"))
        existing = session.scalar(
            select(Standing).where(
                Standing.tournament_id == tid,
                Standing.group_name == row["group_name"],
                Standing.team_id == team_id,
            )
        )
        fields = {
            "matches_played": row.get("matches_played"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "ties": row.get("ties"),
            "no_results": row.get("no_results"),
            "points": row.get("points"),
            "net_run_rate": row.get("net_run_rate"),
            "position": row.get("position"),
            "qualified": row.get("qualified"),
            "source_id": source_id,
            "source_url": doc.get("source_url"),
            "collected_at": collected_at,
        }
        if existing is None:
            session.add(Standing(tournament_id=tid, group_name=row["group_name"],
                                 team_id=team_id, **fields))
            counts["inserted"] += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            counts["updated"] += 1
    session.flush()
    return counts


def load_squads(session: Session, doc: dict[str, Any], source_id: int | None) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "teams_created": 0, "players_created": 0}
    tid = doc["tournament_id"]
    if session.get(Tournament, tid) is None:
        raise ValueError(f"Tournament {tid} not in database; load tournaments first")
    collected_at = _parse_dt(doc.get("collected_at"))
    for squad in doc.get("squads") or []:
        raw_team_id = squad.get("team_id")
        if not raw_team_id:
            continue
        if _ensure_team(session, raw_team_id, squad.get("team_name"), None,
                        raw_team_id.replace("espn_", ""), source_id):
            counts["teams_created"] += 1
        team_id = _resolve_team_id(session, raw_team_id, squad.get("team_name"))
        for p in squad.get("players") or []:
            player = session.get(Player, p["player_id"])
            if player is None:
                session.add(
                    Player(
                        player_id=p["player_id"],
                        full_name=p.get("full_name") or p["player_id"],
                        source_name=SOURCE_NAME,
                        source_player_id=p.get("source_player_id"),
                        batting_style=p.get("batting_style"),
                        bowling_style=p.get("bowling_style"),
                        date_of_birth=_parse_date(p.get("date_of_birth")),
                        source_id=source_id,
                    )
                )
                counts["players_created"] += 1
                session.flush()
            existing = session.scalar(
                select(Squad).where(
                    Squad.tournament_id == tid,
                    Squad.team_id == team_id,
                    Squad.player_id == p["player_id"],
                )
            )
            fields = {
                "role_code": p.get("role_code"),
                "is_captain": bool(p.get("is_captain")),
                "is_wicketkeeper": bool(p.get("is_wicketkeeper")),
                "playing_roles": ", ".join(p.get("playing_roles") or []) or None,
                "announced_at": _parse_date(squad.get("announced_at")),
                "is_withdrawn": bool(p.get("is_withdrawn")),
                "note": p.get("note"),
                "source_id": source_id,
                "source_url": squad.get("source_url"),
                "collected_at": collected_at,
            }
            if existing is None:
                session.add(Squad(tournament_id=tid, team_id=team_id,
                                  player_id=p["player_id"], **fields))
                counts["inserted"] += 1
            else:
                for key, value in fields.items():
                    setattr(existing, key, value)
                counts["updated"] += 1
    session.flush()
    return counts


def load_standings_and_squads(
    session: Session, *, tournament_id: str | None = None
) -> dict[str, Any]:
    root = get_project_root() / "data" / "processed"
    source = session.scalar(select(Source).where(Source.name == SOURCE_NAME))
    source_id = source.source_id if source else None

    ids = sorted(
        {p.stem for p in (root / "standings").glob("*.json")}
        | {p.stem for p in (root / "squads").glob("*.json")}
    )
    if tournament_id:
        ids = [i for i in ids if i == tournament_id]

    report: dict[str, Any] = {}
    for tid in ids:
        entry: dict[str, Any] = {}
        standings = _read(root / "standings" / f"{tid}.json")
        squads = _read(root / "squads" / f"{tid}.json")
        try:
            if standings:
                entry["standings"] = load_standings(session, standings, source_id)
            if squads:
                entry["squads"] = load_squads(session, squads, source_id)
        except ValueError as exc:
            entry["error"] = str(exc)
        report[tid] = entry
    return report
