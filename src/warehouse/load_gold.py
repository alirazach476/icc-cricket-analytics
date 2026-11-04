# ruff: noqa: E501
"""Load the gold layer into PostgreSQL (``analytics`` schema) and DuckDB (Stage 6).

PostgreSQL load = incremental, idempotent, transactional
1. Each table is bulk-loaded (``COPY``) into a temporary staging table.
2. Rows are upserted into the real table (``INSERT .. ON CONFLICT (pk) DO UPDATE``) and only rows
   whose values actually differ are touched, so re-running an unchanged gold layer changes nothing.
3. Keys that vanished from gold are deleted (gold is a full snapshot, so the database mirrors it).
4. Counts per table are written to ``analytics.load_audit``.
Everything runs in one transaction in dependency order, so a failure leaves the previous load intact
and foreign keys are never violated mid-load. Gold is never modified.

DuckDB load = a rebuildable analytical copy (``data/warehouse/cricket_gold.duckdb``, schema ``gold``).
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.warehouse.analytics_schema import (
    AUDIT_DDL,
    AUDIT_TABLE,
    SCHEMA,
    TABLES,
    gold_path,
    pg_type,
    read_gold,
    render_ddl,
    render_design_doc,
    table_ddl,
)

DUCKDB_SCHEMA = "gold"


def duckdb_path(root: Path) -> Path:
    return root / "data" / "warehouse" / "cricket_gold.duckdb"


# --------------------------------------------------------------------------- schema
def create_schema(engine: Engine, root: Path) -> None:
    """Create the analytics schema and tables if missing (idempotent)."""
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        for spec in TABLES:
            for stmt in _split(table_ddl(spec, read_gold(root, spec.name))):
                conn.execute(text(stmt))
        conn.execute(text(AUDIT_DDL))


def _split(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";\n") if s.strip()]


def drop_schema(engine: Engine) -> None:
    """Remove the analytics schema (it is fully rebuildable from gold)."""
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


# --------------------------------------------------------------------------- postgres
def _csv(df: pd.DataFrame) -> io.StringIO:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N", date_format="%Y-%m-%d")
    buf.seek(0)
    return buf


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        # Booleans must serialise as true/false for COPY.
        if pg_type(col, out[col]) == "BOOLEAN":
            out[col] = out[col].astype(object).map(lambda v: None if pd.isna(v) else bool(v))
        elif pd.api.types.is_integer_dtype(out[col].dtype):
            out[col] = out[col].astype("Int64")
    return out


def _upsert_table(conn, spec, df: pd.DataFrame) -> dict[str, int]:
    cols = list(df.columns)
    qcols = ", ".join(f'"{c}"' for c in cols)
    stage = f"stage_{spec.name}"
    target = f"{SCHEMA}.{spec.name}"
    raw = conn.connection  # psycopg2 connection, same transaction
    cur = raw.cursor()
    cur.execute(f"CREATE TEMP TABLE {stage} (LIKE {target} INCLUDING DEFAULTS) ON COMMIT DROP")
    cur.copy_expert(
        f"COPY {stage} ({qcols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", _csv(_prepare(df))
    )
    pk = ", ".join(f'"{c}"' for c in spec.pk)
    non_pk = [c for c in cols if c not in spec.pk]
    if non_pk:
        sets = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in non_pk)
        distinct = " OR ".join(f't."{c}" IS DISTINCT FROM EXCLUDED."{c}"' for c in non_pk)
        conflict = f"DO UPDATE SET {sets} WHERE {distinct}"
    else:
        conflict = "DO NOTHING"
    cur.execute(
        f"INSERT INTO {target} AS t ({qcols}) SELECT {qcols} FROM {stage} "
        f"ON CONFLICT ({pk}) {conflict} RETURNING (xmax = 0)"
    )
    flags = [r[0] for r in cur.fetchall()]
    inserted = sum(1 for f in flags if f)
    updated = len(flags) - inserted
    join = " AND ".join(f't."{c}" = s."{c}"' for c in spec.pk)
    cur.execute(f"DELETE FROM {target} t WHERE NOT EXISTS (SELECT 1 FROM {stage} s WHERE {join})")
    deleted = cur.rowcount
    cur.close()
    return {"inserted": inserted, "updated": updated, "deleted": deleted}


def load_postgres(engine: Engine, root: Path) -> list[dict[str, Any]]:
    """Sync every gold table into ``analytics``. One transaction; returns per-table counts."""
    create_schema(engine, root)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]
    results: list[dict[str, Any]] = []
    frames = {spec.name: read_gold(root, spec.name) for spec in TABLES}
    with engine.begin() as conn:
        conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        for spec in TABLES:  # parents first
            counts = _upsert_table(conn, spec, frames[spec.name])
            results.append({"table": spec.name, "source_rows": len(frames[spec.name]), **counts})
        # Deletions must also respect FKs, so a delete that removes a parent while a stale child
        # still references it would already have failed the transaction (nothing is half-loaded).
        for r in results:
            conn.execute(
                text(
                    f"INSERT INTO {SCHEMA}.{AUDIT_TABLE} (run_id, table_name, source_rows, inserted, "
                    f"updated, deleted) VALUES (:run, :t, :s, :i, :u, :d)"
                ),
                {
                    "run": run_id,
                    "t": r["table"],
                    "s": r["source_rows"],
                    "i": r["inserted"],
                    "u": r["updated"],
                    "d": r["deleted"],
                },
            )
        conn.execute(text(f"ANALYZE {SCHEMA}.fact_deliveries"))
    for r in results:
        r["run_id"] = run_id
    return results


def postgres_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            spec.name: conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.{spec.name}")).scalar_one()
            for spec in TABLES
        }


# --------------------------------------------------------------------------- duckdb
def load_duckdb(root: Path, path: Path | None = None, skip_missing: bool = False) -> dict[str, int]:
    """Rebuild the DuckDB copy from gold Parquet (full refresh, idempotent)."""
    path = path or duckdb_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    con = duckdb.connect(str(path))
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {DUCKDB_SCHEMA}")
        for spec in TABLES:
            src = gold_path(root, spec.name).as_posix()
            if skip_missing and not Path(src).exists():
                continue  # e.g. the synthetic match conditions exist for World Cup matches only
            con.execute(
                f"CREATE OR REPLACE TABLE {DUCKDB_SCHEMA}.{spec.name} AS "
                f"SELECT * FROM read_parquet('{src}')"
            )
            counts[spec.name] = con.execute(
                f"SELECT count(*) FROM {DUCKDB_SCHEMA}.{spec.name}"
            ).fetchone()[0]
    finally:
        con.close()
    return counts


def write_ddl(root: Path) -> Path:
    out = root / "sql" / "schema" / "analytics_schema.sql"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_ddl(root), encoding="utf-8")
    return out


def write_design_doc(root: Path, counts: dict[str, int] | None = None) -> Path:
    out = root / "docs" / "database_design.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_design_doc(root, counts), encoding="utf-8")
    return out
