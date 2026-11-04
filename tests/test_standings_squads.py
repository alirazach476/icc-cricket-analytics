"""Standings / squads parsing and loading (parsers use cached raw ESPNcricinfo pages)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.database.load_standings_squads import load_squads, load_standings
from src.database.models import Base, Player, Squad, Standing, Team, Tournament
from src.parsers.standings_parser import (
    parse_squad_html,
    parse_squad_index_html,
    parse_standings_html,
)

ROOT = Path(__file__).resolve().parents[1]
STANDINGS_HTML = ROOT / "data/raw/standings/T20_M_2007/standings.html"
SQUADS_DIR = ROOT / "data/raw/squads/T20_M_2007"

needs_raw = pytest.mark.skipif(
    not STANDINGS_HTML.exists() or not SQUADS_DIR.exists(),
    reason="raw ESPNcricinfo pages not collected",
)


@needs_raw
def test_parse_standings_t20_2007() -> None:
    parsed = parse_standings_html(
        STANDINGS_HTML.read_text(encoding="utf-8"),
        tournament_id="T20_M_2007",
        source_url="x",
    )
    assert parsed["parse_status"] == "ok"
    assert len(parsed["rows"]) == 20
    assert {r["group_name"] for r in parsed["rows"]} == {f"Group {c}" for c in "ABCDEF"}
    pak = next(r for r in parsed["rows"] if r["group_name"] == "Group F" and r["team_name"] == "Pakistan")
    assert (pak["position"], pak["matches_played"], pak["wins"], pak["points"]) == (1, 3, 3, 6.0)
    assert pak["net_run_rate"] == pytest.approx(0.843)


@needs_raw
def test_parse_squads_t20_2007() -> None:
    index = parse_squad_index_html((SQUADS_DIR / "squads_index.html").read_text(encoding="utf-8"))
    assert len(index) == 12
    slug = index[0].rstrip("/").split("/")[-2]
    parsed = parse_squad_html(
        (SQUADS_DIR / f"{slug}.html").read_text(encoding="utf-8"), tournament_id="T20_M_2007", source_url="x"
    )
    assert parsed["parse_status"] == "ok"
    assert parsed["team_id"].startswith("espn_")
    assert len(parsed["players"]) >= 11
    assert sum(p["is_captain"] for p in parsed["players"]) == 1
    assert all(p["player_id"].startswith("espn_") for p in parsed["players"])


def test_parsers_handle_garbage() -> None:
    assert parse_standings_html("<html></html>", tournament_id="T", source_url="x")["parse_status"] == "failed"
    assert parse_squad_html("<html></html>", tournament_id="T", source_url="x")["parse_status"] == "failed"
    assert parse_squad_index_html("<html></html>") == []


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Tournament(tournament_id="T20_M_2007", tournament_name="WT20 2007", year=2007,
                         format="T20", gender="Men"))
        s.add(Team(team_id="espn_3", team_name="South Africa", short_name="SA"))
        s.commit()
        yield s


def test_load_standings_idempotent_and_reuses_teams(session) -> None:
    doc = {
        "tournament_id": "T20_M_2007",
        "source_url": "u",
        "rows": [
            {"group_name": "Group A", "team_id": "espn_3", "team_name": "South Africa",
             "short_name": "SA", "source_team_id": "3", "position": 1, "matches_played": 2,
             "wins": 2, "losses": 0, "ties": 0, "no_results": 0, "points": 4.0,
             "net_run_rate": 0.974, "qualified": None},
            {"group_name": "Group A", "team_id": "espn_25", "team_name": "Bangladesh",
             "short_name": "BAN", "source_team_id": "25", "position": 2, "matches_played": 2,
             "wins": 1, "losses": 1, "ties": 0, "no_results": 0, "points": 2.0,
             "net_run_rate": 0.149, "qualified": None},
        ],
    }
    first = load_standings(session, doc, None)
    second = load_standings(session, doc, None)
    session.commit()
    assert first == {"inserted": 2, "updated": 0, "teams_created": 1}
    assert second == {"inserted": 0, "updated": 2, "teams_created": 0}
    assert session.scalar(select(func.count()).select_from(Standing)) == 2


def test_load_squads_idempotent_creates_players(session) -> None:
    doc = {
        "tournament_id": "T20_M_2007",
        "squads": [
            {
                "team_id": "espn_3", "team_name": "South Africa", "announced_at": "2007-09-03",
                "source_url": "u",
                "players": [
                    {"player_id": "espn_1", "source_player_id": "1", "full_name": "Graeme Smith",
                     "role_code": "C", "is_captain": True, "is_wicketkeeper": False,
                     "playing_roles": ["Opening Batter"], "date_of_birth": "1981-02-01"},
                    {"player_id": "espn_2", "source_player_id": "2", "full_name": "Mark Boucher",
                     "role_code": "WK", "is_captain": False, "is_wicketkeeper": True,
                     "playing_roles": []},
                ],
            }
        ],
    }
    first = load_squads(session, doc, None)
    second = load_squads(session, doc, None)
    session.commit()
    assert first["inserted"] == 2 and first["players_created"] == 2
    assert second["inserted"] == 0 and second["updated"] == 2
    assert session.scalar(select(func.count()).select_from(Squad)) == 2
    assert session.scalar(select(func.count()).select_from(Player)) == 2
    captain = session.scalar(select(Squad).where(Squad.is_captain.is_(True)))
    assert captain.player_id == "espn_1"


def test_load_requires_known_tournament(session) -> None:
    with pytest.raises(ValueError):
        load_standings(session, {"tournament_id": "NOPE", "rows": []}, None)


def test_derive_qualification_uses_later_matches() -> None:
    from src.parsers.standings_parser import derive_qualification

    matches = [
        {"match_id": "1", "match_date": "2007-09-12", "team1_name": "A", "team2_name": "B"},
        {"match_id": "2", "match_date": "2007-09-13", "team1_name": "A", "team2_name": "C"},
        {"match_id": "3", "match_date": "2007-09-14", "team1_name": "B", "team2_name": "C"},
        {"match_id": "9", "match_date": "2007-09-20", "team1_name": "A", "team2_name": "B"},  # knockout
    ]
    rows = [
        {"group_name": "G", "team_name": "A", "group_match_ids": ["1", "2"], "qualified": None},
        {"group_name": "G", "team_name": "B", "group_match_ids": ["1", "3"], "qualified": None},
        {"group_name": "G", "team_name": "C", "group_match_ids": ["2", "3"], "qualified": None},
        {"group_name": "H", "team_name": "D", "group_match_ids": [], "qualified": None},
    ]
    counts = derive_qualification(rows, matches)
    assert [r["qualified"] for r in rows] == [True, True, False, None]
    assert counts == {"true": 2, "false": 1, "unknown": 1}
