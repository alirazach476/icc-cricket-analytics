"""Parser tests — tournament parser covered in Stage 4; others in Stage 8 / 16."""

from pathlib import Path

from src.parsers.tournament_parser import parse_tournament_html

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tournament_series_minimal.html"


def test_tournament_parser_fixture() -> None:
    parsed = parse_tournament_html(FIXTURE.read_text(encoding="utf-8"))
    assert parsed["discovered_name"] == "ICC Cricket World Cup 2023/24"
    assert parsed["extracted_fields"]["number_of_teams"] == 10
