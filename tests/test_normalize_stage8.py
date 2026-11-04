"""Stage 8 normalization / cleaning tests."""

from __future__ import annotations

import json
from pathlib import Path

from src.parsers.batting_parser import parse_batting_from_scorecard
from src.parsers.innings_parser import parse_innings_from_scorecard
from src.parsers.match_parser import parse_match_from_scorecard
from src.transformations.clean_deliveries import clean_delivery_list
from src.transformations.clean_matches import clean_match
from src.transformations.clean_players import merge_player_records
from src.transformations.standardize_teams import canonical_team_name, standardize_team_record

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _minimal_scorecard() -> dict:
    return {
        "match_id": "1384392",
        "tournament_id": "ODI_M_2023",
        "source_url": "https://example/scorecard",
        "source_name": "ESPNcricinfo",
        "parse_status": "ok",
        "scorecard_status": "complete",
        "warnings": [],
        "match": {
            "match_id": "1384392",
            "tournament_id": "ODI_M_2023",
            "source_match_id": "1384392",
            "match_date": "2023-10-05",
            "venue": "Narendra Modi Stadium, Ahmedabad",
            "city": "Ahmedabad",
            "toss_winner_id": "espn_5",
            "toss_decision": 2,
            "winner_id": "espn_5",
            "team1_id": "espn_1",
            "team2_id": "espn_5",
            "result_type": "RESULT",
            "result_margin": "New Zealand won by 9 wickets",
            "source_url": "https://example/scorecard",
        },
        "teams": [
            {"team_id": "espn_1", "source_team_id": "1", "team_name": "England", "abbreviation": "ENG"},
            {"team_id": "espn_5", "source_team_id": "5", "team_name": "New Zealand", "abbreviation": "NZ"},
        ],
        "players": [
            {"player_id": "espn_1", "source_player_id": "1", "player_name": "A", "batting_name": "A"},
            {"player_id": "espn_1", "source_player_id": "1", "player_name": "A Longer", "batting_name": "A"},
        ],
        "innings": [
            {
                "innings_id": "1384392_1",
                "match_id": "1384392",
                "innings_number": 1,
                "innings_type": "standard",
                "batting_team_id": "espn_1",
                "bowling_team_id": "espn_5",
                "total_runs": 282,
                "wickets": 9,
                "overs": 50,
                "extras": 10,
            }
        ],
        "batting_scorecards": [
            {
                "match_id": "1384392",
                "innings_number": 1,
                "player_id": "espn_1",
                "player_name": "A",
                "team_id": "espn_1",
                "batting_position": 1,
                "runs": 10,
                "balls_faced": 12,
            }
        ],
        "bowling_scorecards": [],
        "fielding_scorecards": [],
    }


def test_canonical_team_aliases() -> None:
    assert canonical_team_name("UAE") == "United Arab Emirates"
    assert canonical_team_name("Holland") == "Netherlands"
    assert canonical_team_name("Some Unknown XI") == "Some Unknown XI"


def test_clean_match_toss_mapping() -> None:
    cleaned = clean_match(
        {"match_id": "1", "toss_decision": 2, "tournament_id": "ODI_M_2023"},
        manifest={"team1_name": "England", "team2_name": "NZ"},
    )
    assert cleaned is not None
    assert cleaned["toss_decision"] == "field"
    assert cleaned["team2_name"] == "New Zealand"


def test_merge_players_by_source_id_not_name() -> None:
    merged = merge_player_records(
        [
            {"player_id": "espn_1", "source_player_id": "1", "player_name": "A"},
            {"player_id": "espn_1", "source_player_id": "1", "player_name": "A Longer"},
            {"player_id": "espn_2", "source_player_id": "2", "player_name": "A"},
        ]
    )
    assert len(merged) == 2
    a = next(p for p in merged if p["player_id"] == "espn_1")
    assert a["full_name"] == "A Longer"


def test_entity_parsers_from_scorecard() -> None:
    sc = _minimal_scorecard()
    match = parse_match_from_scorecard(sc, ball_by_ball_status="complete")
    assert match is not None
    assert match["toss_decision"] == "field"
    assert match["ball_by_ball_status"] == "complete"
    innings = parse_innings_from_scorecard(sc)
    assert len(innings) == 1
    batting = parse_batting_from_scorecard(sc)
    assert batting[0]["runs"] == 10
    teams = [standardize_team_record(t) for t in sc["teams"]]
    assert teams[0]["team_name"] == "England"


def test_clean_deliveries_legal_ball_numbers() -> None:
    deliveries = clean_delivery_list(
        [
            {
                "match_id": "m",
                "innings_number": 1,
                "delivery_sequence": 1,
                "batter_runs": 0,
                "extra_runs": 1,
                "total_runs": 1,
                "is_wide": True,
                "is_legal_delivery": False,
            },
            {
                "match_id": "m",
                "innings_number": 1,
                "delivery_sequence": 2,
                "batter_runs": 4,
                "extra_runs": 0,
                "total_runs": 4,
                "is_wide": False,
                "is_legal_delivery": True,
            },
        ]
    )
    assert deliveries[0]["legal_ball_number"] is None
    assert deliveries[1]["legal_ball_number"] == 1


def test_cricsheet_fixture_clean_pipeline() -> None:
    payload = json.loads((FIXTURES / "cricsheet_match_minimal.json").read_text(encoding="utf-8"))
    from src.parsers.ball_by_ball_parser import parse_cricsheet_match_json

    parsed = parse_cricsheet_match_json(payload, match_id="1384392")
    cleaned = clean_delivery_list(parsed["deliveries"])
    assert len(cleaned) == 5
    assert cleaned[2]["is_wide"] is True
    assert cleaned[3]["is_wicket"] is True
