"""Read-only access to the gold DuckDB for the dashboard (cached).

The World Cup gold database is the default. The React backend can point the same queries at the
Champions Trophy or World Test Championship gold databases (identical table layout) with
``set_competition``; the cache key includes the database so results never mix.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = PROJECT_ROOT / "data" / "warehouse"
DB_PATHS = {
    "wc": WAREHOUSE / "cricket_gold.duckdb",
    "ct": WAREHOUSE / "cricket_gold_ct.duckdb",
    "wtc": WAREHOUSE / "cricket_gold_wtc.duckdb",
    "wc27": WAREHOUSE / "cricket_gold_wc27.duckdb",
}
DB_PATH = DB_PATHS["wc"]
# The selected competition is per request / per thread (a ContextVar), not a process-wide global: a server
# answers /api/meta and /api/page at the same time, and one must never switch the other's database.
_competition: ContextVar[str] = ContextVar("competition", default="wc")


def set_competition(code: str) -> None:
    _competition.set(code if code in DB_PATHS else "wc")


def competition() -> str:
    return _competition.get()


def db_available() -> bool:
    return DB_PATHS[competition()].exists()


@st.cache_data(ttl=3600, show_spinner=False)
def _run(sql: str, params: tuple, db: str) -> pd.DataFrame:
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute(sql, list(params)).fetchdf()
    finally:
        con.close()


def run(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a parameterised read-only query. A fresh connection per call keeps threads safe."""
    return _run(sql, tuple(params), str(DB_PATHS[competition()]))
