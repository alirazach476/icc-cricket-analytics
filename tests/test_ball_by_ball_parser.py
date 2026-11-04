"""Stage 7 ball-by-ball parser tests."""

from __future__ import annotations

import json
from pathlib import Path

from src.parsers.ball_by_ball_parser import (
    normalize_team_name,
    parse_cricsheet_match_json,
    parse_espn_commentary_html,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_espn_commentary_partial_fixture() -> None:
    html = (FIXTURES / "commentary_espn_partial.html").read_text(encoding="utf-8")
    parsed = parse_espn_commentary_html(
        html,
        match_id="1384392",
        source_url="https://www.espncricinfo.com/example/ball-by-ball-commentary",
    )
    assert parsed["parse_status"] == "ok"
    assert parsed["ball_by_ball_status"] == "partial"
    assert len(parsed["deliveries"]) == 3
    first = parsed["deliveries"][0]
    assert first["delivery_id"] == "1384392_1_1"
    assert first["batter_runs"] == 0
    assert first["source_name"] == "ESPNcricinfo"
    wide = parsed["deliveries"][2]
    assert wide["is_wide"] is True
    assert wide["extras_type"] == "wide"
    assert wide["is_legal_delivery"] is False
    assert "full length" in (first["commentary_text"] or "")


def test_parse_espn_missing_next_data() -> None:
    parsed = parse_espn_commentary_html("<html><body>no data</body></html>", match_id="x")
    assert parsed["parse_status"] == "failed"
    assert parsed["ball_by_ball_status"] == "unavailable"
    assert parsed["deliveries"] == []


def test_parse_cricsheet_match_minimal() -> None:
    payload = json.loads((FIXTURES / "cricsheet_match_minimal.json").read_text(encoding="utf-8"))
    parsed = parse_cricsheet_match_json(
        payload,
        match_id="1384392",
        source_url="cricsheet://minimal.json",
    )
    assert parsed["parse_status"] == "ok"
    assert parsed["ball_by_ball_status"] == "complete"
    assert len(parsed["deliveries"]) == 5
    wicket = parsed["deliveries"][3]
    assert wicket["is_wicket"] is True
    assert wicket["dismissal_type"] == "caught"
    assert wicket["dismissed_player_id"] == "JM Bairstow"
    assert wicket["fielder_id"] == "DP Conway"
    wide = parsed["deliveries"][2]
    assert wide["is_wide"] is True
    assert wide["delivery_id"] == "1384392_1_3"
    second_inn = parsed["deliveries"][4]
    assert second_inn["innings_number"] == 2
    assert second_inn["delivery_sequence"] == 1


def test_normalize_team_name() -> None:
    assert normalize_team_name("New Zealand") == "new zealand"
    assert normalize_team_name("West Indies") == "west indies"
    assert normalize_team_name("U.A.E.") == "u a e"
