"""Stage 6 scorecard parser tests."""

from pathlib import Path

from src.parsers.scorecard_parser import parse_scorecard_html

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "scorecard_modern_odi_minimal.html"


def test_parse_modern_odi_scorecard_fixture() -> None:
    parsed = parse_scorecard_html(
        FIXTURE.read_text(encoding="utf-8"),
        match_id="1384439",
        tournament_id="ODI_M_2023",
        source_url="https://www.espncricinfo.com/example/full-scorecard",
    )
    assert parsed["parse_status"] == "ok"
    assert parsed["scorecard_status"] == "complete"
    assert parsed["match"]["winner_id"] == "espn_2"
    assert parsed["match"]["player_of_match_id"] == "espn_530011"
    assert len(parsed["innings"]) == 2
    assert parsed["innings"][0]["total_runs"] == 240
    assert parsed["batting_scorecards"][0]["player_name"] == "Rohit Sharma"
    assert parsed["batting_scorecards"][0]["dismissal_type"] == "caught"
    assert parsed["bowling_scorecards"][0]["player_name"] == "Mitchell Starc"
    assert parsed["bowling_scorecards"][0]["wickets"] == 3
    catches = [f for f in parsed["fielding_scorecards"] if f["player_id"] == "espn_530011"]
    assert catches and catches[0]["catches"] == 1
