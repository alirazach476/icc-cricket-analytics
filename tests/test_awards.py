"""Award loading: exact ESPN-name resolution, squad cross-check, idempotency (synthetic data)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.database.load_awards import load_awards, read_awards
from src.database.models import Base, Player, Squad, Team, Tournament, TournamentAward


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(
            Tournament(
                tournament_id="T1", tournament_name="T", year=2007, format="T20", gender="Men"
            )
        )
        s.add_all(
            [
                Team(team_id="espn_6", team_name="India"),
                Team(team_id="espn_7", team_name="Pakistan"),
            ]
        )
        s.add_all(
            [
                Player(player_id="espn_1", full_name="Star Player", source_name="ESPNcricinfo"),
                Player(
                    player_id="cricsheet_star_player",
                    full_name="Star Player",
                    source_name="Cricsheet",
                ),
                Player(player_id="espn_2", full_name="Twin", source_name="ESPNcricinfo"),
                Player(player_id="espn_3", full_name="Twin", source_name="ESPNcricinfo"),
            ]
        )
        s.add(Squad(tournament_id="T1", team_id="espn_6", player_id="espn_1"))
        s.commit()
        yield s


def _row(player="Star Player", team="India"):
    return {
        "tournament_id": "T1",
        "award_type": "player_of_the_tournament",
        "player_name": player,
        "team_name": team,
        "source": "test",
    }


def test_resolves_espn_id_not_cricsheet_and_is_idempotent(session) -> None:
    assert load_awards(session, [_row()])["inserted"] == 1
    report = load_awards(session, [_row()])
    assert report["updated"] == 1 and report["winner_not_in_collected_squad"] == []
    award = session.scalars(select(TournamentAward)).one()
    assert (award.player_id, award.team_id) == ("espn_1", "espn_6")
    assert session.scalar(select(func.count()).select_from(TournamentAward)) == 1


def test_winner_missing_from_squad_is_reported_not_hidden(session) -> None:
    report = load_awards(session, [_row(team="Pakistan")])
    assert report["winner_not_in_collected_squad"] == ["T1: Star Player (Pakistan)"]


def test_ambiguous_or_unknown_names_fail_loudly(session) -> None:
    with pytest.raises(ValueError, match="matches 2 ESPN players"):
        load_awards(session, [_row(player="Twin")])
    with pytest.raises(ValueError, match="matches 0"):
        load_awards(session, [_row(player="Nobody")])
    with pytest.raises(ValueError, match="unknown tournament"):
        load_awards(session, [{**_row(), "tournament_id": "NOPE"}])


def test_shipped_awards_file_covers_all_seventeen_editions() -> None:
    rows = read_awards()
    assert len(rows) == 17 and len({r["tournament_id"] for r in rows}) == 17
