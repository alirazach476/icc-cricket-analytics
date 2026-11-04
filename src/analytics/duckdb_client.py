"""DuckDB access helpers for analytics marts (Stage 13)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

from src.utils.config import get_settings, resolve_path
from src.warehouse.duckdb_warehouse import get_duckdb_path


def resolve_analytics_duckdb(*, tournament_id: str | None = None) -> Path:
    """Prefer full warehouse; fall back to tournament-scoped file if needed."""
    full = get_duckdb_path()
    if tournament_id:
        scoped = get_duckdb_path(tournament_id=tournament_id)
        # Prefer full DB when it contains analytics_marts; else scoped
        if full.exists():
            return full
        if scoped.exists():
            return scoped
    if full.exists():
        return full
    settings = get_settings()
    rel = ((settings.get("database") or {}).get("duckdb") or {}).get("path")
    return resolve_path(rel or "data/warehouse/cricket.duckdb")


@contextmanager
def duckdb_connection(*, tournament_id: str | None = None, read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
    path = resolve_analytics_duckdb(tournament_id=tournament_id)
    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB warehouse not found at {path}. Run sync_warehouse + dbt first."
        )
    con = duckdb.connect(str(path), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def read_sql(sql: str, *, tournament_id: str | None = None, params: list | None = None) -> pd.DataFrame:
    with duckdb_connection(tournament_id=tournament_id) as con:
        if params:
            return con.execute(sql, params).df()
        return con.execute(sql).df()


def marts_available(*, tournament_id: str | None = None) -> bool:
    try:
        with duckdb_connection(tournament_id=tournament_id) as con:
            schemas = {r[0] for r in con.execute("select schema_name from information_schema.schemata").fetchall()}
            return "analytics_marts" in schemas
    except FileNotFoundError:
        return False
