"""Stage 9 validation tests."""

from __future__ import annotations

from src.validation.delivery_validation import validate_deliveries
from src.validation.innings_validation import validate_innings
from src.validation.match_validation import validate_match
from src.validation.player_validation import validate_players
from src.validation.validate_dataset import validate_match_bundle


def _bundle(**overrides):
    base = {
        "match_id": "m1",
        "tournament_id": "ODI_M_2023",
        "scorecard_status": "complete",
        "ball_by_ball_status": "complete",
        "delivery_count": 2,
        "match": {
            "match_id": "m1",
            "tournament_id": "ODI_M_2023",
            "match_date": "2023-10-05",
            "team1_id": "espn_1",
            "team2_id": "espn_2",
            "toss_winner_id": "espn_1",
            "toss_decision": "bat",
            "winner_id": "espn_2",
            "scorecard_status": "complete",
            "ball_by_ball_status": "complete",
        },
        "teams": [
            {"team_id": "espn_1", "team_name": "England"},
            {"team_id": "espn_2", "team_name": "New Zealand"},
        ],
        "players": [
            {
                "player_id": "espn_10",
                "full_name": "Batter A",
                "source_name": "ESPNcricinfo",
                "source_player_id": "10",
            }
        ],
        "innings": [
            {
                "innings_id": "m1_1",
                "match_id": "m1",
                "innings_number": 1,
                "batting_team_id": "espn_1",
                "bowling_team_id": "espn_2",
                "total_runs": 15,
                "wickets": 1,
                "extras": 5,
            }
        ],
        "batting_scorecards": [
            {
                "match_id": "m1",
                "innings_number": 1,
                "player_id": "espn_10",
                "runs": 10,
            }
        ],
        "bowling_scorecards": [],
        "fielding_scorecards": [],
    }
    base.update(overrides)
    return base


def test_match_required_fields() -> None:
    bundle = _bundle()
    bundle["match"]["team1_id"] = None
    issues = validate_match(bundle)
    assert any(i["code"] == "match_required_field" for i in issues)


def test_innings_batting_extras_match() -> None:
    ok = validate_innings(_bundle())
    assert not any(i["code"] == "innings_batting_extras_mismatch" for i in ok)

    bad = _bundle()
    bad["innings"][0]["total_runs"] = 99
    issues = validate_innings(bad)
    assert any(i["code"] == "innings_batting_extras_mismatch" for i in issues)


def test_delivery_innings_runs_match() -> None:
    bundle = _bundle()
    deliveries_doc = {
        "deliveries": [
            {
                "delivery_id": "m1_1_1",
                "match_id": "m1",
                "innings_number": 1,
                "delivery_sequence": 1,
                "batter_runs": 10,
                "extra_runs": 0,
                "total_runs": 10,
            },
            {
                "delivery_id": "m1_1_2",
                "match_id": "m1",
                "innings_number": 1,
                "delivery_sequence": 2,
                "batter_runs": 0,
                "extra_runs": 5,
                "total_runs": 5,
            },
        ]
    }
    issues = validate_deliveries(bundle, deliveries_doc=deliveries_doc)
    assert not any(i["code"] == "delivery_innings_runs_mismatch" for i in issues)

    deliveries_doc["deliveries"][0]["total_runs"] = 1
    deliveries_doc["deliveries"][0]["batter_runs"] = 1
    issues = validate_deliveries(bundle, deliveries_doc=deliveries_doc)
    assert any(i["code"] == "delivery_innings_runs_mismatch" for i in issues)


def test_player_duplicate_source_identity() -> None:
    bundle = _bundle(
        players=[
            {
                "player_id": "espn_10",
                "full_name": "A",
                "source_name": "ESPNcricinfo",
                "source_player_id": "10",
            },
            {
                "player_id": "espn_11",
                "full_name": "B",
                "source_name": "ESPNcricinfo",
                "source_player_id": "10",
            },
        ]
    )
    issues = validate_players(bundle)
    assert any(i["code"] == "player_duplicate_source_identity" for i in issues)


def test_validate_match_bundle_ok_without_deliveries_file(tmp_path, monkeypatch) -> None:
    # complete BBB without deliveries file should error
    bundle = _bundle()
    from src.validation import validate_dataset as vd

    monkeypatch.setattr(vd, "get_project_root", lambda: tmp_path)
    result = validate_match_bundle(bundle, root=tmp_path)
    assert result["ok"] is False
    assert any(i["code"] == "deliveries_missing_for_complete_bbb" for i in result["issues"])
