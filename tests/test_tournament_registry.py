"""Stage 2 tournament registry tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.discovery.source_registry import load_source_registry
from src.discovery.tournament_registry import (
    EXPECTED_TOURNAMENT_IDS,
    TournamentRecord,
    TournamentRegistry,
    load_tournament_registry,
    sync_tournament_manifest,
)


def test_load_registry_has_sixteen_unique_ids() -> None:
    registry = load_tournament_registry()
    ids = [t.tournament_id for t in registry.tournaments]
    assert len(ids) == 16
    assert set(ids) == EXPECTED_TOURNAMENT_IDS


def test_registry_summary() -> None:
    summary = load_tournament_registry().summary()
    assert summary["odi"] == 6
    assert summary["t20"] == 10
    assert summary["completed"] == 16
    assert summary["with_source_url"] == 16
    assert summary["match_counts_verified"] == 0


def test_all_source_urls_present() -> None:
    registry = load_tournament_registry()
    for tournament in registry.tournaments:
        assert tournament.source_url, tournament.tournament_id
        assert "espncricinfo.com" in str(tournament.source_url)


def test_match_counts_remain_unverified() -> None:
    registry = load_tournament_registry()
    assert all(t.number_of_matches is None for t in registry.tournaments)


def test_t20_2026_marked_completed_with_winner() -> None:
    tournament = load_tournament_registry().get("T20_M_2026")
    assert tournament.completion_status == "completed"
    assert tournament.winner == "India"
    assert tournament.runner_up == "New Zealand"
    assert tournament.host_country == "India; Sri Lanka"


def test_by_format_filters() -> None:
    registry = load_tournament_registry()
    assert len(registry.by_format("ODI")) == 6
    assert len(registry.by_format("T20")) == 10


def test_duplicate_tournament_id_rejected() -> None:
    base = load_tournament_registry().tournaments[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        TournamentRegistry(tournaments=[base, base])


def test_out_of_scope_id_rejected() -> None:
    with pytest.raises(ValidationError):
        TournamentRecord(
            tournament_id="ODI_M_1999",
            tournament_name="Out of scope",
            year=1999,
            format="ODI",
            gender="Men",
        )


def test_id_must_match_format_and_year() -> None:
    with pytest.raises(ValidationError):
        TournamentRecord(
            tournament_id="ODI_M_2023",
            tournament_name="Mismatch",
            year=2019,
            format="ODI",
            gender="Men",
        )


def test_source_registry_loads() -> None:
    sources = load_source_registry()
    assert sources.primary.name == "ESPNcricinfo"
    assert sources.respect_robots is True
    assert any(s.name == "Cricsheet" for s in sources.supplementary)


def test_sync_manifest_writes_completion_status(tmp_path) -> None:
    # Sync against the real project path; assert header includes completion_status
    path = sync_tournament_manifest()
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert "completion_status" in header
    assert "T20_M_2026" in path.read_text(encoding="utf-8")
