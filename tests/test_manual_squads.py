"""Manual squad loading: explicit ids, cross-check against scorecards, idempotency (synthetic data)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.database.load_manual_squads import load_manual_squads, read_manual_squads
from src.database.models import BattingScorecard, Base, Match, Player, Squad, Team, Tournament


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(
            Tournament(
                tournament_id="T1", tournament_name="T", year=2026, format="T20", gender="Men"
            )
        )
        s.add_all(
            [Team(team_id="espn_11", team_name="USA"), Team(team_id="espn_2", team_name="Other")]
        )
        s.add_all(
            [
                Player(player_id="espn_1", full_name="Captain Kay", source_name="ESPNcricinfo"),
                Player(
                    player_id="espn_2", full_name="Spelt Differently", source_name="ESPNcricinfo"
                ),
                Player(player_id="espn_3", full_name="Played Unlisted", source_name="ESPNcricinfo"),
            ]
        )
        s.add(Match(match_id="m1", tournament_id="T1", team1_id="espn_11", team2_id="espn_2"))
        s.flush()
        s.add(
            BattingScorecard(match_id="m1", innings_number=1, player_id="espn_3", team_id="espn_11")
        )
        s.commit()
        yield s


def _row(name, pid="", role="P", cap="false"):
    return {
        "tournament_id": "T1",
        "team_name": "USA",
        "player_name": name,
        "player_id": pid,
        "role_code": role,
        "is_captain": cap,
        "is_wicketkeeper": "false",
        "playing_role": "Batter",
        "source": "test",
        "note": "",
    }


def test_load_uses_explicit_id_for_spelling_variants_and_is_idempotent(session) -> None:
    rows = [_row("Captain Kay", role="C", cap="true"), _row("Spelt Differentlyy", pid="espn_2")]
    assert load_manual_squads(session, rows)["inserted"] == 2
    assert load_manual_squads(session, rows)["updated"] == 2
    assert session.scalar(select(func.count()).select_from(Squad)) == 2
    cap = session.scalars(select(Squad).where(Squad.is_captain.is_(True))).one()
    assert cap.player_id == "espn_1" and cap.role_code == "C"


def test_player_who_played_but_is_not_listed_is_reported(session) -> None:
    report = load_manual_squads(session, [_row("Captain Kay")])
    assert report["players_who_played_but_not_in_supplied_squad"] == ["T1/espn_11: espn_3"]


def test_unknown_name_fails_loudly(session) -> None:
    with pytest.raises(ValueError, match="matches 0"):
        load_manual_squads(session, [_row("Nobody Here")])


def test_shipped_file_is_a_full_fifteen_with_one_captain() -> None:
    rows = read_manual_squads()
    assert len(rows) == 15
    assert sum(r["is_captain"] == "true" for r in rows) == 1
