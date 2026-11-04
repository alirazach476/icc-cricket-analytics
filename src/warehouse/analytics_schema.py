# ruff: noqa: E501
"""Analytical database design (Stage 5): a star schema in the Postgres ``analytics`` schema.

The operational tables in ``public`` stay as the as-collected, pre-resolution layer. ``analytics``
holds the cleaned gold layer: conformed dimensions, fact tables at a stated grain, and marts.

Design rules
* Column *names* and *order* come from the gold Parquet files, so gold stays the single source.
* Column *types* come from the Parquet dtypes, with the few exceptions in ``TYPE_OVERRIDES``.
* Everything else that a database should guarantee (primary keys, foreign keys, checks, indexes)
  is declared here, explicitly, once. The DDL is generated from this file (``render_ddl``), so the
  design document, the migration and the loader cannot drift apart.
* Foreign keys are real constraints, not conventions: gold was verified to have no orphans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

SCHEMA = "analytics"
AUDIT_TABLE = "load_audit"

# Columns that hold ISO dates stored as text in Parquet.
DATE_COLUMNS = {"match_date", "start_date", "end_date", "date", "date_of_birth"}
# dtype cannot be inferred (all-null in the source, or JSON kept as text on purpose).
TYPE_OVERRIDES = {
    "possible_duplicate_of": "TEXT",
    "name_variants": "TEXT",
    "cricsheet_names": "TEXT",
    "cricsheet_ids": "TEXT",
    "_ingested_at": "TIMESTAMPTZ",
}


@dataclass(frozen=True)
class FK:
    column: str
    ref_table: str
    ref_column: str


@dataclass(frozen=True)
class TableSpec:
    name: str
    kind: str  # dimension | fact | mart
    grain: str  # one row per ...
    pk: tuple[str, ...]
    fks: tuple[FK, ...] = ()
    indexes: tuple[tuple[str, ...], ...] = ()
    checks: tuple[tuple[str, str], ...] = ()  # (constraint name, SQL expression)
    not_null: tuple[str, ...] = ()
    comment: str = ""
    extra: dict = field(default_factory=dict)


T = "tournament_id"
_P = "player_id"
_TEAM = "team_id"


def _fk_team(*cols: str) -> tuple[FK, ...]:
    return tuple(FK(c, "dim_teams", "team_id") for c in cols)


# Load order = dependency order (parents first); deletes run in reverse.
TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        "dim_dates",
        "dimension",
        "calendar day (2003-2026 span of the tournaments)",
        ("date_key",),
        not_null=("date",),
        checks=(("month_range", "month between 1 and 12"),),
    ),
    TableSpec(
        "dim_teams",
        "dimension",
        "national team (aliases from the source merged)",
        ("team_id",),
        not_null=("team_name",),
        extra={"unique": [("team_key",)]},
    ),
    TableSpec(
        "dim_players",
        "dimension",
        "player; Cricsheet and ESPN identities unified",
        (_P,),
        not_null=("full_name",),
        indexes=(("full_name",),),
    ),
    TableSpec(
        "dim_venues",
        "dimension",
        "ground, after reviewed alias merges (config/venue_aliases.csv)",
        ("venue_id",),
        not_null=("venue_name",),
    ),
    TableSpec(
        "dim_tournaments",
        "dimension",
        "tournament edition (format + year)",
        (T,),
        fks=_fk_team("winner_team_id", "runner_up_team_id")
        + (FK("player_of_tournament_id", "dim_players", "player_id"),),
        not_null=("tournament_name", "format", "year"),
        checks=(("format_known", "format in ('ODI','T20')"),),
        indexes=(("format", "year"),),
    ),
    TableSpec(
        "fact_matches",
        "fact",
        "match",
        ("match_id",),
        fks=(
            FK(T, "dim_tournaments", T),
            FK("venue_id", "dim_venues", "venue_id"),
            FK("date_key", "dim_dates", "date_key"),
            FK("player_of_match_id", "dim_players", "player_id"),
        )
        + _fk_team(
            "team1_id",
            "team2_id",
            "toss_winner_id",
            "winner_id",
            "loser_id",
            "batting_first_team_id",
            "batting_second_team_id",
        ),
        not_null=(T, "format", "match_date", "team1_id", "team2_id"),
        checks=(
            ("teams_differ", "team1_id <> team2_id"),
            (
                "winner_is_participant",
                "winner_id is null or winner_id in (team1_id, team2_id)",
            ),
            ("format_known", "format in ('ODI','T20')"),
        ),
        indexes=((T,), ("match_date",), ("venue_id",), ("winner_id",), ("format", "year")),
    ),
    TableSpec(
        "fact_innings",
        "fact",
        "innings of a match (Super Over included, flagged)",
        ("innings_id",),
        fks=(FK("match_id", "fact_matches", "match_id"), FK(T, "dim_tournaments", T))
        + _fk_team("batting_team_id", "bowling_team_id"),
        not_null=("match_id", "innings_number", "batting_team_id", "bowling_team_id"),
        checks=(
            ("teams_differ", "batting_team_id <> bowling_team_id"),
            ("wickets_range", "wickets is null or wickets between 0 and 10"),
            ("runs_nonneg", "total_runs is null or total_runs >= 0"),
        ),
        indexes=(("match_id",), (T,), ("batting_team_id",)),
    ),
    TableSpec(
        "fact_deliveries",
        "fact",
        "ball bowled (ball-by-ball matches only; Super Over included, flagged)",
        ("delivery_id",),
        fks=(
            FK("match_id", "fact_matches", "match_id"),
            FK("innings_id", "fact_innings", "innings_id"),
            FK(T, "dim_tournaments", T),
            FK("batter_id", "dim_players", "player_id"),
            FK("non_striker_id", "dim_players", "player_id"),
            FK("bowler_id", "dim_players", "player_id"),
            FK("dismissed_player_id", "dim_players", "player_id"),
            FK("fielder_id", "dim_players", "player_id"),
        )
        + _fk_team("batting_team_id", "bowling_team_id"),
        not_null=("match_id", "innings_id", "batter_id", "bowler_id", "batting_team_id"),
        checks=(
            ("runs_nonneg", "batter_runs >= 0 and extra_runs >= 0 and total_runs >= 0"),
            ("total_is_sum", "total_runs = batter_runs + extra_runs"),
            (
                "phase_known",
                "phase is null or phase in ('powerplay','middle','death','super_over')",
            ),
        ),
        indexes=(
            ("match_id", "innings_number"),
            ("innings_id",),
            ("batter_id",),
            ("bowler_id",),
            ("tournament_id", "phase"),
        ),
    ),
    TableSpec(
        "fact_player_performances",
        "fact",
        "player in a match (batting, bowling and fielding combined)",
        ("match_id", _P),
        fks=(
            FK("match_id", "fact_matches", "match_id"),
            FK(_P, "dim_players", "player_id"),
            FK(T, "dim_tournaments", T),
        )
        + _fk_team("team_id", "opposition_team_id"),
        not_null=("team_id",),
        checks=(
            ("batting_nonneg", "runs is null or runs >= 0"),
            ("bowling_nonneg", "wickets is null or wickets between 0 and 10"),
        ),
        indexes=((_P,), (T,), ("team_id",)),
    ),
    TableSpec(
        "fact_super_over_performances",
        "fact",
        "player role in a Super Over (kept apart so regular statistics are not polluted)",
        ("match_id", "innings_number", _P, "role"),
        fks=(FK("match_id", "fact_matches", "match_id"), FK(_P, "dim_players", "player_id"))
        + _fk_team("team_id"),
        checks=(("role_known", "role in ('bat','bowl')"),),
    ),
    TableSpec(
        "fact_tournament_standings",
        "fact",
        "team in a group/points table of a tournament",
        (T, "group_name", "team_id"),
        fks=(FK(T, "dim_tournaments", T),) + _fk_team("team_id"),
        checks=(("played_matches_add_up", "wins + losses + ties + no_results <= matches_played"),),
    ),
    TableSpec(
        "synthetic_match_conditions",
        "synthetic",
        "match (SYNTHETIC pitch, weather and day/night placeholders; not real data)",
        ("match_id",),
        fks=(FK("match_id", "fact_matches", "match_id"),),
        not_null=("is_synthetic", "day_night", "pitch_type"),
        checks=(
            ("is_synthetic_only", "is_synthetic = true"),
            ("day_night_known", "day_night in ('day','day_night')"),
            (
                "pitch_known",
                "pitch_type in ('batting_friendly','balanced','bowling_friendly','spin_friendly')",
            ),
            ("humidity_range", "humidity_pct between 0 and 100"),
            ("rain_range", "rain_probability_pct between 0 and 100"),
        ),
        comment="synthetic placeholder; excluded from real analytics",
    ),
    TableSpec(
        "fact_squads",
        "fact",
        "player in a team's tournament squad (with age and whether they played)",
        (T, "team_id", _P),
        fks=(FK(T, "dim_tournaments", T), FK(_P, "dim_players", "player_id")) + _fk_team("team_id"),
        not_null=("full_name",),
        checks=(("matches_nonneg", "matches_played >= 0"),),
        indexes=((T, "team_id"),),
    ),
    TableSpec(
        "mart_batting",
        "mart",
        "player x tournament x team (batting)",
        (_P, T, "team_id"),
        fks=(FK(_P, "dim_players", "player_id"), FK(T, "dim_tournaments", T)) + _fk_team("team_id"),
        indexes=((T,),),
    ),
    TableSpec(
        "mart_batting_career",
        "mart",
        "player x format (batting career in World Cups)",
        (_P, "format"),
        fks=(FK(_P, "dim_players", "player_id"),),
    ),
    TableSpec(
        "mart_bowling",
        "mart",
        "player x tournament x team (bowling)",
        (_P, T, "team_id"),
        fks=(FK(_P, "dim_players", "player_id"), FK(T, "dim_tournaments", T)) + _fk_team("team_id"),
        indexes=((T,),),
    ),
    TableSpec(
        "mart_bowling_career",
        "mart",
        "player x format (bowling career in World Cups)",
        (_P, "format"),
        fks=(FK(_P, "dim_players", "player_id"),),
    ),
    TableSpec(
        "mart_team_performance",
        "mart",
        "team x tournament",
        (_TEAM, T),
        fks=_fk_team("team_id") + (FK(T, "dim_tournaments", T),),
        indexes=((T,),),
    ),
    TableSpec(
        "mart_tournament_summary",
        "mart",
        "tournament",
        (T,),
        fks=(FK(T, "dim_tournaments", T),),
    ),
    TableSpec(
        "mart_data_coverage",
        "mart",
        "tournament (what data exists, incl. ball-by-ball gaps)",
        (T,),
        fks=(FK(T, "dim_tournaments", T),),
    ),
)
BY_NAME = {t.name: t for t in TABLES}


# --------------------------------------------------------------------------- types
def pg_type(column: str, series: pd.Series) -> str:
    if column in TYPE_OVERRIDES:
        return TYPE_OVERRIDES[column]
    if column in DATE_COLUMNS:
        return "DATE"
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    non_null = series.dropna()
    if len(non_null) and all(
        isinstance(v, (bool,)) or str(type(v)).endswith("bool_'>") for v in non_null
    ):
        return "BOOLEAN"
    return "TEXT"


def gold_path(root: Path, table: str) -> Path:
    """Location of a table's Parquet. Synthetic tables live in data/synthetic, never in gold."""
    spec = BY_NAME.get(table)
    base = "synthetic" if spec is not None and spec.kind == "synthetic" else "gold"
    return (
        root
        / "data"
        / base
        / (table.removeprefix("synthetic_") if base == "synthetic" else table)
        / "part-0.parquet"
    )


def read_gold(root: Path, table: str) -> pd.DataFrame:
    df = pd.read_parquet(gold_path(root, table))
    for col in df.columns:
        if pg_type(col, df[col]) == "BOOLEAN" and df[col].dtype == object:
            df[col] = df[col].astype("boolean")
    return df


# --------------------------------------------------------------------------- DDL
def _q(name: str) -> str:
    return f'"{name}"'


def table_ddl(spec: TableSpec, df: pd.DataFrame) -> str:
    missing = [c for c in (*spec.pk, *(f.column for f in spec.fks)) if c not in df.columns]
    if missing:
        raise ValueError(f"{spec.name}: spec references columns not in gold: {missing}")
    keyset = set(spec.pk) | set(spec.not_null)
    lines = []
    for col in df.columns:
        nn = " NOT NULL" if col in keyset else ""
        lines.append(f"    {_q(col)} {pg_type(col, df[col])}{nn}")
    lines.append(f"    CONSTRAINT pk_{spec.name} PRIMARY KEY ({', '.join(map(_q, spec.pk))})")
    for cols in spec.extra.get("unique", []):
        lines.append(f"    CONSTRAINT uq_{spec.name}_{'_'.join(cols)} UNIQUE ({', '.join(cols)})")
    for fk in spec.fks:
        lines.append(
            f"    CONSTRAINT fk_{spec.name}_{fk.column} FOREIGN KEY ({_q(fk.column)}) "
            f"REFERENCES {SCHEMA}.{fk.ref_table} ({_q(fk.ref_column)})"
        )
    for name, expr in spec.checks:
        lines.append(f"    CONSTRAINT ck_{spec.name}_{name} CHECK ({expr})")
    out = [f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{spec.name} (\n" + ",\n".join(lines) + "\n);"]
    comment = f"{spec.kind}: one row per {spec.grain}".replace("'", "''")  # escape quotes in the description
    out.append(f"COMMENT ON TABLE {SCHEMA}.{spec.name} IS '{comment}';")
    # Indexes: every FK column is indexed (joins + cascading checks) unless it leads the PK.
    wanted = {tuple(i) for i in spec.indexes}
    for fk in spec.fks:
        if spec.pk[0] != fk.column:
            wanted.add((fk.column,))
    for cols in sorted(wanted):
        out.append(
            f"CREATE INDEX IF NOT EXISTS ix_{spec.name}_{'_'.join(cols)} "
            f"ON {SCHEMA}.{spec.name} ({', '.join(map(_q, cols))});"
        )
    return "\n".join(out)


AUDIT_DDL = f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.{AUDIT_TABLE} (
    run_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    source_rows BIGINT NOT NULL,
    inserted BIGINT NOT NULL,
    updated BIGINT NOT NULL,
    deleted BIGINT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_{AUDIT_TABLE} PRIMARY KEY (run_id, table_name)
);"""


def render_ddl(root: Path) -> str:
    parts = [
        "-- GENERATED by src/warehouse/analytics_schema.py - do not edit by hand.",
        f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};",
        "",
    ]
    for spec in TABLES:
        parts.append(table_ddl(spec, read_gold(root, spec.name)))
        parts.append("")
    parts.append(AUDIT_DDL)
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- design document
def render_erd() -> str:
    """Mermaid ER diagram of the dimension/fact relationships (marts omitted for readability)."""
    lines = ["erDiagram"]
    for spec in TABLES:
        if spec.kind == "mart":
            continue
        for fk in spec.fks:
            lines.append(f'    {fk.ref_table} ||--o{{ {spec.name} : "{fk.column}"')
    return "\n".join(dict.fromkeys(lines))


def render_design_doc(root: Path, counts: dict[str, int] | None = None) -> str:
    NL = "\n"
    rows = []
    for spec in TABLES:
        n = f"{counts[spec.name]:,}" if counts and spec.name in counts else ""
        rows.append(
            f"| `{spec.name}` | {spec.kind} | {spec.grain} | `{', '.join(spec.pk)}` | "
            f"{len(spec.fks)} | {len(spec.checks)} | {n} |"
        )
    return f"""# Analytical database design (Stage 5)

Generated from `src/warehouse/analytics_schema.py` - edit the spec there, not this file.

## Layout

| Where | What | Role |
|---|---|---|
| PostgreSQL `public` | tables as collected, identities not yet unified | operational / audit layer (Stage 3 rules) |
| PostgreSQL `{SCHEMA}` | star schema loaded from `data/gold` | analytics, SQL, dbt, dashboard, ML features |
| DuckDB `data/warehouse/cricket_gold.duckdb` (schema `gold`) | full copy of gold | fast local analytics, notebooks |

## Tables

| Table | Kind | One row per | Primary key | FKs | Checks | Rows |
|---|---|---|---|---|---|---|
{NL.join(rows)}

## Relationships

```mermaid
{render_erd()}
```

## Design decisions

* **Star schema.** Facts at a stated grain; conformed dimensions (`dim_teams`, `dim_players`,
  `dim_venues`, `dim_tournaments`, `dim_dates`) shared by every fact. Marts are pre-aggregated
  and rebuildable; they never feed back into facts.
* **Surrogate vs natural keys.** Natural keys are used (ESPN match/player/team ids, `ODI_M_2023`
  style tournament ids) because they are stable, human-readable and already unique; the
  Cricsheet-to-ESPN identity unification is done in silver, so the dimension key is one id per person.
* **Integrity is enforced, not assumed.** Every foreign key is a real constraint (gold has zero
  orphans), plus `CHECK`s for value ranges and cricket rules (winner is a participant, a team does
  not play itself, wickets 0-10, ball runs add up). Dimensions that a fact may lack (winner of a
  tie, fielder on a non-catch) are nullable FKs.
* **Super Overs are excluded from regular statistics** by being flagged on innings/deliveries and
  kept in a separate fact (`fact_super_over_performances`).
* **Indexes.** Primary keys; every foreign-key column (join and cascade-check support); plus the
  query paths we use: `(format, year)`, `match_date`, `(match_id, innings_number)`,
  `(tournament_id, phase)`, player ids on deliveries. Indexes are declared in the spec.
* **No fabricated data.** Missing ball-by-ball for 164 matches stays missing and is explained per
  match in `fact_matches.ball_by_ball_gap_reason` and summarised in `mart_data_coverage`.

## Load strategy (Stage 6)

* Gold is a full snapshot, so loads are *sync*, not append: bulk `COPY` into a temp staging table,
  `INSERT .. ON CONFLICT (pk) DO UPDATE .. WHERE <row differs>`, then delete keys no longer in gold.
* **Idempotent:** re-running on unchanged gold inserts/updates/deletes 0 rows.
* **Incremental:** only rows that changed are written; counts per table go to `{SCHEMA}.{AUDIT_TABLE}`.
* **Atomic:** one transaction in dependency order; a failure leaves the previous load untouched.
* **Migrations:** Alembic revision `20261103_0002` creates the schema from the generated
  `sql/schema/analytics_schema.sql`; changing a table later is a new revision.
"""
