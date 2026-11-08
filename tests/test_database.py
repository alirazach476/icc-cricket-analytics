"""Database Stage 3 tests — require local PostgreSQL when available."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from src.database.connection import check_connection, get_engine, reset_engine_cache, session_scope
from src.database.models import Base, Tournament
from src.database.repository import get_tournament, upsert_tournament
from src.database.schema import create_schema, list_tables
from src.database.seed_data import seed_reference_data
from src.discovery.tournament_registry import EXPECTED_TOURNAMENT_IDS


def _postgres_available() -> bool:
    try:
        reset_engine_cache()
        return check_connection()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL is not reachable (start with: docker compose up -d postgres)",
)


@pytest.fixture(scope="module")
def engine():
    reset_engine_cache()
    eng = get_engine()
    create_schema(eng)
    return eng


def test_required_tables_exist(engine) -> None:
    tables = set(list_tables(engine))
    required = {
        "tournaments",
        "teams",
        "players",
        "matches",
        "match_teams",
        "innings",
        "deliveries",
        "batting_scorecards",
        "bowling_scorecards",
        "fielding_scorecards",
        "standings",
        "tournament_awards",
        "match_events",
        "sources",
        "collection_runs",
        "data_quality_results",
    }
    assert required.issubset(tables)


def test_orm_metadata_matches_required_count() -> None:
    assert len(Base.metadata.tables) >= 16


def test_seed_tournaments_and_sources(engine) -> None:
    with session_scope() as session:
        result = seed_reference_data(session)
    assert result["tournament_count"] == 17
    assert "ESPNcricinfo" in result["sources"]
    assert "Cricsheet" in result["sources"]
    assert set(result["tournament_ids"]) == EXPECTED_TOURNAMENT_IDS


def test_tournament_upsert_is_idempotent(engine) -> None:
    with session_scope() as session:
        seed_reference_data(session)
        upsert_tournament(
            session,
            {
                "tournament_id": "ODI_M_2023",
                "tournament_name": "ICC Cricket World Cup 2023",
                "year": 2023,
                "format": "ODI",
                "gender": "Men",
                "host_country": "India",
                "collection_status": "not_started",
                "completion_status": "completed",
            },
        )
        row = get_tournament(session, "ODI_M_2023")
        assert row is not None
        assert row.host_country == "India"


def test_foreign_keys_declared(engine) -> None:
    inspector = inspect(engine)
    match_fks = inspector.get_foreign_keys("matches")
    referred = {fk["referred_table"] for fk in match_fks}
    assert "tournaments" in referred
    delivery_fks = inspector.get_foreign_keys("deliveries")
    referred_d = {fk["referred_table"] for fk in delivery_fks}
    assert "matches" in referred_d
    assert "innings" in referred_d


def test_no_fabricated_matches(engine) -> None:
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM matches")).scalar_one()
    assert count == 0
