"""Stage 11 DuckDB / Parquet warehouse tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.database.connection import check_connection, reset_engine_cache
from src.warehouse.duckdb_warehouse import get_duckdb_path, query_duckdb, sync_warehouse


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


def test_sync_warehouse_odi_2023_writes_duckdb_and_parquet(tmp_path: Path, monkeypatch) -> None:
    # Keep artifacts under project warehouse; assert expected counts for ODI 2023
    report = sync_warehouse(
        tournament_id="ODI_M_2023",
        tables=["tournaments", "matches", "innings", "deliveries", "teams"],
        write_parquet=True,
        replace_duckdb=True,
    )
    assert report["claims_complete_coverage"] is False
    assert Path(report["duckdb_path"]).exists()
    assert report["tables"]["matches"]["rows"] == 48
    assert report["tables"]["tournaments"]["rows"] == 1
    assert report["tables"]["deliveries"]["rows"] == 21195
    assert report["tables"]["teams"]["rows"] == 10

    for table, stats in report["tables"].items():
        path = Path(stats["parquet"])
        assert path.exists(), table
        assert path.stat().st_size > 0

    df = query_duckdb(
        "SELECT COUNT(*) AS n FROM matches",
        tournament_id="ODI_M_2023",
    )
    assert int(df.iloc[0]["n"]) == 48


def test_get_duckdb_path_scoped() -> None:
    full = get_duckdb_path()
    scoped = get_duckdb_path(tournament_id="ODI_M_2023")
    assert full.name == "cricket.duckdb"
    assert scoped.name == "cricket_ODI_M_2023.duckdb"
