"""Load tournament awards from config/tournament_awards.csv into tournament_awards.

Names are resolved to ESPN player/team ids (exact name match, ESPN ids only). A missing or
ambiguous name is an error, never a guess. Each winner is cross-checked against the collected
squad for that tournament; mismatches are reported, not hidden.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Player, Squad, Team, Tournament, TournamentAward
from src.utils.config import get_project_root

AWARD_NAMES = {"player_of_the_tournament": "Player of the Tournament"}


def read_awards(path: Path | None = None) -> list[dict[str, str]]:
    path = path or get_project_root() / "config" / "tournament_awards.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _espn_player(session: Session, name: str) -> str:
    ids = session.scalars(
        select(Player.player_id).where(Player.full_name == name, Player.player_id.like("espn_%"))
    ).all()
    if len(ids) != 1:
        raise ValueError(f"player {name!r} matches {len(ids)} ESPN players: {ids}")
    return ids[0]


def _team(session: Session, name: str) -> str:
    ids = session.scalars(select(Team.team_id).where(Team.team_name == name)).all()
    if len(ids) != 1:
        raise ValueError(f"team {name!r} matches {len(ids)} teams: {ids}")
    return ids[0]


def load_awards(session: Session, rows: list[dict[str, str]]) -> dict[str, Any]:
    inserted = updated = 0
    not_in_squad: list[str] = []
    for row in rows:
        tid, kind = row["tournament_id"], row["award_type"]
        if session.get(Tournament, tid) is None:
            raise ValueError(f"unknown tournament {tid}")
        if kind not in AWARD_NAMES:
            raise ValueError(f"unknown award type {kind}")
        player_id = _espn_player(session, row["player_name"])
        team_id = _team(session, row["team_name"])

        in_squad = session.scalar(
            select(Squad.squad_id).where(
                Squad.tournament_id == tid, Squad.team_id == team_id, Squad.player_id == player_id
            )
        )
        if in_squad is None:
            not_in_squad.append(f"{tid}: {row['player_name']} ({row['team_name']})")

        award_id = f"{tid}_{kind}"
        fields = {
            "tournament_id": tid,
            "award_type": kind,
            "player_id": player_id,
            "team_id": team_id,
            "award_name": AWARD_NAMES[kind],
            "source_url": row.get("source") or None,
        }
        existing = session.get(TournamentAward, award_id)
        if existing is None:
            session.add(TournamentAward(award_id=award_id, **fields))
            inserted += 1
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
            updated += 1
    session.flush()
    return {"inserted": inserted, "updated": updated, "winner_not_in_collected_squad": not_in_squad}
