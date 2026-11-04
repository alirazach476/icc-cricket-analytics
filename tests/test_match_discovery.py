"""Stage 5 match discovery tests (offline fixtures)."""

from __future__ import annotations

from pathlib import Path

from src.discovery.match_discovery import discover_matches
from src.parsers.match_list_parser import map_match_stage, parse_match_schedule_html

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "match_schedule_minimal.html"


def test_map_match_stage_from_source_titles() -> None:
    assert map_match_stage("Final", 1) == "Final"
    assert map_match_stage("1st Semi-Final", 3) == "Semifinal"
    assert map_match_stage("1st Match", 0) == "Group Stage"
    assert map_match_stage("Super Eight", 0) == "Super Eight"
    assert map_match_stage("Super Six", 0) == "Super Six"
    assert map_match_stage("3rd Place Play-off", 0) == "Third Place"


def test_parse_schedule_fixture() -> None:
    parsed = parse_match_schedule_html(
        FIXTURE.read_text(encoding="utf-8"),
        tournament_id="ODI_M_2023",
        source_url="https://www.espncricinfo.com/series/example/match-schedule-fixtures-and-results",
    )
    assert parsed["parse_status"] == "ok"
    assert len(parsed["matches"]) == 2
    first, final = parsed["matches"]
    assert first["match_id"] == "1384392"
    assert first["match_stage"] == "Group Stage"
    assert first["team1_name"] == "England"
    assert first["team2_name"] == "New Zealand"
    assert first["scorecard_url"].endswith("/full-scorecard")
    assert first["commentary_url"].endswith("/ball-by-ball-commentary")
    assert final["match_stage"] == "Final"
    assert final["match_id"] == "1384439"


def test_dry_run_match_discovery() -> None:
    report = discover_matches(tournament_ids=["ODI_M_2023"], live=False)
    assert report["total_tournaments"] == 1
    assert report["total_matches_discovered"] == 0
    assert report["tournaments"][0]["access_status"] == "dry_run"
