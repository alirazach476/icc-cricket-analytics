"""Load user-supplied squads from config/manual_squads.csv into the squads table.

Used when a source page lacked a squad. Names resolve to ESPN ids by exact match unless the CSV
gives an explicit player_id; a missing or ambiguous name is an error, never a guess. Players who
played for the team in that tournament are cross-checked against the supplied list.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.load_awards import _espn_player, _team
from src.database.models import BattingScorecard, BowlingScorecard, Match, Player, Squad, Tournament
from src.utils.config import get_project_root


def read_manual_squads(path: Path | None = None) -> list[dict[str, str]]:
    path = path or get_project_root() / "config" / "manual_squads.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _flag(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def load_manual_squads(session: Session, rows: list[dict[str, str]]) -> dict[str, Any]:
    inserted = updated = 0
    seen: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        tid = row["tournament_id"]
        if session.get(Tournament, tid) is None:
            raise ValueError(f"unknown tournament {tid}")
        team_id = _team(session, row["team_name"])
        player_id = row.get("player_id") or _espn_player(session, row["player_name"])
        if session.get(Player, player_id) is None:
            raise ValueError(f"player id {player_id} not in players")
        seen.setdefault((tid, team_id), set()).add(player_id)

        fields = {
            "role_code": row.get("role_code") or "P",
            "is_captain": _flag(row.get("is_captain", "")),
            "is_wicketkeeper": _flag(row.get("is_wicketkeeper", "")),
            "playing_roles": row.get("playing_role") or None,
            "is_withdrawn": False,
            "note": row.get("note") or None,
            "source_url": row.get("source") or None,
        }
        existing = session.scalar(
            select(Squad).where(
                Squad.tournament_id == tid, Squad.team_id == team_id, Squad.player_id == player_id
            )
        )
        if existing is None:
            session.add(Squad(tournament_id=tid, team_id=team_id, player_id=player_id, **fields))
            inserted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            updated += 1
    session.flush()

    played_not_in_list: list[str] = []
    for (tid, team_id), listed in seen.items():
        played = set(
            session.scalars(
                select(BattingScorecard.player_id)
                .join(Match, Match.match_id == BattingScorecard.match_id)
                .where(Match.tournament_id == tid, BattingScorecard.team_id == team_id)
            ).all()
        ) | set(
            session.scalars(
                select(BowlingScorecard.player_id)
                .join(Match, Match.match_id == BowlingScorecard.match_id)
                .where(Match.tournament_id == tid, BowlingScorecard.team_id == team_id)
            ).all()
        )
        played_not_in_list += [f"{tid}/{team_id}: {p}" for p in sorted(played - listed)]
    return {
        "inserted": inserted,
        "updated": updated,
        "players_who_played_but_not_in_supplied_squad": played_not_in_list,
    }
