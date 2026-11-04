"""Sync PostgreSQL warehouse tables into DuckDB + Parquet (Stage 11)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from sqlalchemy import text

from src.database.connection import get_engine
from src.utils.config import get_project_root, get_settings, resolve_path
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

WAREHOUSE_TABLES = (
    "sources",
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
    "squads",
    "collection_runs",
    "data_quality_results",
)

MATCH_SCOPED_TABLES = {
    "matches",
    "match_teams",
    "innings",
    "deliveries",
    "batting_scorecards",
    "bowling_scorecards",
    "fielding_scorecards",
}


def get_duckdb_path(*, tournament_id: str | None = None) -> Path:
    settings = get_settings()
    rel = ((settings.get("database") or {}).get("duckdb") or {}).get("path") or "data/warehouse/cricket.duckdb"
    path = resolve_path(rel)
    if tournament_id:
        path = path.with_name(f"cricket_{tournament_id}.duckdb")
    ensure_dir(path.parent)
    return path


def get_parquet_dir(*, tournament_id: str | None = None) -> Path:
    settings = get_settings()
    rel = ((settings.get("paths") or {}).get("parquet_dir") or "data/warehouse/parquet")
    base = ensure_dir(resolve_path(rel))
    if tournament_id:
        return ensure_dir(base / tournament_id)
    return base


def _match_ids_for_tournament(engine, tournament_id: str) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT match_id FROM matches WHERE tournament_id = :tid ORDER BY match_id"),
            {"tid": tournament_id},
        ).fetchall()
    return [str(r[0]) for r in rows]


def _read_table(
    engine,
    table: str,
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
) -> pd.DataFrame:
    if table == "sources":
        return pd.read_sql(text("SELECT * FROM sources ORDER BY source_id"), engine)

    if table == "tournaments":
        if tournament_id:
            return pd.read_sql(
                text("SELECT * FROM tournaments WHERE tournament_id = :tid"),
                engine,
                params={"tid": tournament_id},
            )
        return pd.read_sql(text("SELECT * FROM tournaments ORDER BY year, format"), engine)

    if table == "collection_runs":
        if tournament_id:
            return pd.read_sql(
                text(
                    "SELECT * FROM collection_runs "
                    "WHERE tournament_id = :tid OR tournament_id IS NULL "
                    "ORDER BY collection_run_id"
                ),
                engine,
                params={"tid": tournament_id},
            )
        return pd.read_sql(text("SELECT * FROM collection_runs ORDER BY collection_run_id"), engine)

    if table == "data_quality_results":
        if tournament_id:
            return pd.read_sql(
                text(
                    "SELECT * FROM data_quality_results "
                    "WHERE tournament_id = :tid OR tournament_id IS NULL "
                    "ORDER BY result_id"
                ),
                engine,
                params={"tid": tournament_id},
            )
        return pd.read_sql(text("SELECT * FROM data_quality_results ORDER BY result_id"), engine)

    if table == "teams" and tournament_id:
        return pd.read_sql(
            text(
                """
                SELECT DISTINCT t.*
                FROM teams t
                WHERE t.team_id IN (
                    SELECT team1_id FROM matches WHERE tournament_id = :tid AND team1_id IS NOT NULL
                    UNION
                    SELECT team2_id FROM matches WHERE tournament_id = :tid AND team2_id IS NOT NULL
                    UNION
                    SELECT toss_winner_id FROM matches WHERE tournament_id = :tid AND toss_winner_id IS NOT NULL
                    UNION
                    SELECT winner_id FROM matches WHERE tournament_id = :tid AND winner_id IS NOT NULL
                    UNION
                    SELECT batting_team_id FROM innings i
                      JOIN matches m ON m.match_id = i.match_id
                     WHERE m.tournament_id = :tid AND i.batting_team_id IS NOT NULL
                    UNION
                    SELECT bowling_team_id FROM innings i
                      JOIN matches m ON m.match_id = i.match_id
                     WHERE m.tournament_id = :tid AND i.bowling_team_id IS NOT NULL
                )
                ORDER BY t.team_name
                """
            ),
            engine,
            params={"tid": tournament_id},
        )

    if table == "players" and tournament_id:
        return pd.read_sql(
            text(
                """
                SELECT DISTINCT p.*
                FROM players p
                WHERE p.player_id IN (
                    SELECT b.player_id
                      FROM batting_scorecards b
                      JOIN matches m ON m.match_id = b.match_id
                     WHERE m.tournament_id = :tid
                    UNION
                    SELECT b.player_id
                      FROM bowling_scorecards b
                      JOIN matches m ON m.match_id = b.match_id
                     WHERE m.tournament_id = :tid
                    UNION
                    SELECT f.player_id
                      FROM fielding_scorecards f
                      JOIN matches m ON m.match_id = f.match_id
                     WHERE m.tournament_id = :tid
                    UNION
                    SELECT m.player_of_match_id
                      FROM matches m
                     WHERE m.tournament_id = :tid AND m.player_of_match_id IS NOT NULL
                    UNION
                    SELECT d.batter_id
                      FROM deliveries d
                      JOIN matches m ON m.match_id = d.match_id
                     WHERE m.tournament_id = :tid AND d.batter_id IS NOT NULL
                    UNION
                    SELECT d.non_striker_id
                      FROM deliveries d
                      JOIN matches m ON m.match_id = d.match_id
                     WHERE m.tournament_id = :tid AND d.non_striker_id IS NOT NULL
                    UNION
                    SELECT d.bowler_id
                      FROM deliveries d
                      JOIN matches m ON m.match_id = d.match_id
                     WHERE m.tournament_id = :tid AND d.bowler_id IS NOT NULL
                    UNION
                    SELECT d.dismissed_player_id
                      FROM deliveries d
                      JOIN matches m ON m.match_id = d.match_id
                     WHERE m.tournament_id = :tid AND d.dismissed_player_id IS NOT NULL
                    UNION
                    SELECT d.fielder_id
                      FROM deliveries d
                      JOIN matches m ON m.match_id = d.match_id
                     WHERE m.tournament_id = :tid AND d.fielder_id IS NOT NULL
                )
                ORDER BY p.player_id
                """
            ),
            engine,
            params={"tid": tournament_id},
        )

    if table in MATCH_SCOPED_TABLES and tournament_id:
        if match_ids is not None and len(match_ids) == 0:
            return pd.DataFrame()
        return pd.read_sql(
            text(
                f"""
                SELECT t.*
                FROM {table} t
                JOIN matches m ON m.match_id = t.match_id
                WHERE m.tournament_id = :tid
                """
            ),
            engine,
            params={"tid": tournament_id},
        )

    if table == "matches":
        return pd.read_sql(text("SELECT * FROM matches ORDER BY match_date, match_id"), engine)
    if table == "teams":
        return pd.read_sql(text("SELECT * FROM teams ORDER BY team_name"), engine)
    if table == "players":
        return pd.read_sql(text("SELECT * FROM players ORDER BY player_id"), engine)

    return pd.read_sql(text(f"SELECT * FROM {table}"), engine)


def sync_warehouse(
    *,
    tournament_id: str | None = None,
    tables: list[str] | None = None,
    write_parquet: bool = True,
    replace_duckdb: bool = False,
) -> dict[str, Any]:
    """Pull Postgres tables into DuckDB and optionally write Parquet files.

    Never fabricates rows — only mirrors what exists in PostgreSQL.
    Tournament-scoped syncs write a separate DuckDB file and parquet subfolder
    so they do not clobber the full warehouse.
    """
    selected = list(tables or WAREHOUSE_TABLES)
    unknown = [t for t in selected if t not in WAREHOUSE_TABLES]
    if unknown:
        raise ValueError(f"Unknown warehouse tables: {unknown}")

    started = utc_now_iso()
    duckdb_path = get_duckdb_path(tournament_id=tournament_id)
    parquet_dir = get_parquet_dir(tournament_id=tournament_id)

    if replace_duckdb and duckdb_path.exists():
        duckdb_path.unlink()
        logger.info("Removed existing DuckDB file for rebuild: %s", duckdb_path)

    engine = get_engine()
    match_ids: list[str] | None = None
    if tournament_id:
        match_ids = _match_ids_for_tournament(engine, tournament_id)
        logger.info("Warehouse sync scoped to %s (%s matches)", tournament_id, len(match_ids))

    con = duckdb.connect(str(duckdb_path))
    table_stats: dict[str, Any] = {}
    try:
        for table in selected:
            df = _read_table(
                engine,
                table,
                tournament_id=tournament_id,
                match_ids=match_ids,
            )
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = pd.to_datetime(df[col], utc=True)

            view_name = f"_df_{table}"
            con.register(view_name, df)
            con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM {view_name}')
            con.unregister(view_name)

            row_count = int(len(df))
            parquet_path = None
            if write_parquet:
                out = parquet_dir / f"{table}.parquet"
                # Escape path for DuckDB string literal
                out_sql = str(out).replace("\\", "/").replace("'", "''")
                con.execute(
                    f'COPY (SELECT * FROM "{table}") TO \'{out_sql}\' '
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
                parquet_path = str(out)

            table_stats[table] = {"rows": row_count, "parquet": parquet_path}
            logger.info("Synced %s rows=%s parquet=%s", table, row_count, parquet_path)
    finally:
        con.close()

    manifest = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "tournament_id": tournament_id,
        "duckdb_path": str(duckdb_path),
        "parquet_dir": str(parquet_dir),
        "tables": table_stats,
        "total_rows": sum(int(v["rows"]) for v in table_stats.values()),
        "claims_complete_coverage": False,
        "notes": (
            "DuckDB/Parquet mirror PostgreSQL contents only. "
            "Tournament-scoped exports use a separate DuckDB file under data/warehouse/."
        ),
    }
    manifest_name = f"warehouse_manifest_{tournament_id or 'all'}.json"
    manifest_path = ensure_dir(get_project_root() / "data" / "warehouse") / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def query_duckdb(sql: str, *, tournament_id: str | None = None) -> pd.DataFrame:
    """Run a read-only SQL query against the local DuckDB warehouse."""
    con = duckdb.connect(str(get_duckdb_path(tournament_id=tournament_id)), read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()
