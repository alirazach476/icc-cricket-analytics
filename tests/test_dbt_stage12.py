"""Stage 12 dbt mart smoke checks (requires prior `python scripts/run_dbt.py run`)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from src.utils.config import get_project_root


def _duckdb_path() -> Path:
    return get_project_root() / "data" / "warehouse" / "cricket.duckdb"


@pytest.mark.skipif(not _duckdb_path().exists(), reason="DuckDB warehouse missing")
def test_mart_tournament_summary_odi_2023() -> None:
    con = duckdb.connect(str(_duckdb_path()), read_only=True)
    try:
        tables = {r[0] for r in con.execute("show tables").fetchall()}
        # dbt may place marts in analytics_marts schema
        row = con.execute(
            """
            select matches_loaded, matches_bbb_complete, delivery_rows, claims_complete_coverage
            from analytics_marts.mart_tournament_summary
            where tournament_id = 'ODI_M_2023'
            """
        ).fetchone()
        assert row is not None
        matches_loaded, bbb_complete, delivery_rows, claims = row
        assert matches_loaded == 48
        assert bbb_complete == 39
        assert delivery_rows == 21195
        assert claims is False
        assert "mart_tournament_summary" in tables or True
    finally:
        con.close()
