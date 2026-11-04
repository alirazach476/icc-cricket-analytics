"""Discovery / registry tests — expanded further in Stage 4 / Stage 5 / Stage 16."""

from src.discovery import EXPECTED_TOURNAMENT_IDS, load_tournament_registry
from src.utils.config import load_tournaments


def test_tournament_registry_has_exactly_sixteen_editions() -> None:
    tournaments = load_tournaments()
    assert len(tournaments) == 16


def test_tournament_ids_are_unique() -> None:
    tournaments = load_tournaments()
    ids = [t["tournament_id"] for t in tournaments]
    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_TOURNAMENT_IDS


def test_validated_registry_matches_loader() -> None:
    registry = load_tournament_registry()
    plain = load_tournaments()
    assert [t.tournament_id for t in registry.tournaments] == [
        row["tournament_id"] for row in plain
    ]
