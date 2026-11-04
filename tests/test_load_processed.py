"""Stage 10 DB load tests."""

from __future__ import annotations

import pytest

from src.database.connection import check_connection, reset_engine_cache, session_scope
from src.database.load_processed import load_processed, resolve_player_id
from src.database.models import Delivery, Match
from src.database.schema import create_schema
from src.database.seed_data import seed_reference_data


def _postgres_available() -> bool:
    try:
        reset_engine_cache()
        return check_connection()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL is not reachable",
)


def test_resolve_player_id_cricsheet_name() -> None:
    pid, stub = resolve_player_id("JM Bairstow")
    assert pid == "cricsheet_jm_bairstow"
    assert stub is not None
    assert stub["source_name"] == "Cricsheet"
    pid2, stub2 = resolve_player_id("espn_123")
    assert pid2 == "espn_123"
    assert stub2 is None


def test_load_single_odi_2023_match() -> None:
    from sqlalchemy import func, select

    from src.database.connection import get_engine

    reset_engine_cache()
    create_schema(get_engine())
    with session_scope() as session:
        seed_reference_data(session)

    report = load_processed(match_ids=["1384392"], dry_run=False)
    assert report["summary"]["ok"] == 1
    assert report["summary"]["failed"] == 0

    with session_scope() as session:
        match = session.get(Match, "1384392")
        assert match is not None
        assert match.tournament_id == "ODI_M_2023"
        assert match.toss_decision == "field"
        delivery_count = session.scalar(
            select(func.count()).select_from(Delivery).where(Delivery.match_id == "1384392")
        )
        assert delivery_count == 525
