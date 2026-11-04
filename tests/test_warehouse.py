"""Stage 5/6: schema spec, Postgres/DuckDB loads, gold quality rules, and data-fix regressions."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from src.validation import validate_gold
from src.validation.rules import validate_rule_ids
from src.warehouse.analytics_schema import BY_NAME, SCHEMA, TABLES, read_gold, render_ddl
from src.warehouse.load_gold import load_duckdb, load_postgres, postgres_counts

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"

needs_gold = pytest.mark.skipif(not (GOLD / "fact_matches").exists(), reason="gold not built")


@pytest.fixture(scope="module")
def engine():
    from src.database.connection import get_engine

    eng = get_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("select 1"))
            has = conn.execute(text("select to_regclass('analytics.fact_matches')")).scalar()
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL not reachable")
    if has is None:
        pytest.skip("analytics schema not loaded; run scripts/load_warehouse.py")
    return eng


# --------------------------------------------------------------------------- spec
@needs_gold
def test_spec_matches_gold_columns_and_dependency_order() -> None:
    seen: set[str] = set()
    for spec in TABLES:
        df = read_gold(ROOT, spec.name)
        cols = set(df.columns)
        assert set(spec.pk) <= cols, spec.name
        assert not df.duplicated(list(spec.pk)).any(), f"{spec.name}: duplicate primary keys"
        assert df[list(spec.pk)].notna().all().all(), f"{spec.name}: null key"
        for fk in spec.fks:
            assert fk.column in cols, (spec.name, fk.column)
            # Parents must load first, except self-contained dimensions.
            assert fk.ref_table in seen, f"{spec.name} loads before its parent {fk.ref_table}"
            ref = read_gold(ROOT, fk.ref_table)[fk.ref_column]
            orphans = ~df[fk.column].dropna().isin(ref)
            assert not orphans.any(), f"{spec.name}.{fk.column} has {int(orphans.sum())} orphans"
        seen.add(spec.name)
    real = {n for n, sp in BY_NAME.items() if sp.kind != "synthetic"}
    assert real == {p.parent.name for p in GOLD.glob("*/part-0.parquet")}


@needs_gold
def test_ddl_is_deterministic_and_has_constraints() -> None:
    a, b = render_ddl(ROOT), render_ddl(ROOT)
    assert a == b
    assert a.count("PRIMARY KEY") == len(TABLES) + 1  # + load_audit
    assert "FOREIGN KEY" in a and "CHECK" in a and "CREATE INDEX" in a


# --------------------------------------------------------------------------- duckdb
@needs_gold
def test_duckdb_copy_matches_gold(tmp_path: Path) -> None:
    counts = load_duckdb(ROOT, tmp_path / "t.duckdb")
    for spec in TABLES:
        assert counts[spec.name] == len(read_gold(ROOT, spec.name)), spec.name


# --------------------------------------------------------------------------- postgres
@needs_gold
def test_postgres_counts_match_gold(engine) -> None:
    db = postgres_counts(engine)
    for spec in TABLES:
        assert db[spec.name] == len(read_gold(ROOT, spec.name)), spec.name


@needs_gold
def test_reload_is_idempotent(engine) -> None:
    results = load_postgres(engine, ROOT)
    assert all(r["inserted"] == r["updated"] == r["deleted"] == 0 for r in results), results


def test_database_enforces_integrity(engine) -> None:
    with engine.connect() as conn:
        kinds = dict(
            conn.execute(
                text(
                    "select contype, count(*) from pg_constraint c join pg_namespace n "
                    "on n.oid = c.connamespace where n.nspname = :s group by 1"
                ),
                {"s": SCHEMA},
            ).fetchall()
        )
    assert kinds.get("p", 0) >= len(TABLES)
    assert kinds.get("f", 0) >= 40
    assert kinds.get("c", 0) >= 10


def test_foreign_key_rejects_orphan(engine) -> None:
    with pytest.raises(Exception, match="foreign key|violates"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"insert into {SCHEMA}.fact_innings (innings_id, match_id, innings_number, "
                    "batting_team_id, bowling_team_id) values ('x_1', 'no_such_match', 1, "
                    "'espn_1', 'espn_2')"
                )
            )


def test_gold_quality_rules_run_clean(engine) -> None:
    from src.validation.validate_data_quality import run_all

    rules = list(validate_gold.RULES)
    validate_rule_ids(rules)
    results, errors = run_all(engine, rules)
    assert errors.empty, errors
    pooled = results.groupby("rule_id")[["total", "failed"]].sum()
    # Guarantees the data is expected to keep (not merely "rules execute").
    for rule in (
        "gold.match_has_result",
        "gold.match_has_innings",
        "gold.innings_runs_match_deliveries",
        "gold.performance_runs_match_scorecard_total",
        "gold.standings_wins_match_results",
        "gold.ball_by_ball_gap_explained",
    ):
        assert pooled.loc[rule, "failed"] == 0, rule
    # Documented, explained residuals: do not let them grow silently.
    assert pooled.loc["gold.innings_wickets_match_deliveries", "failed"] <= 1


# --------------------------------------------------------------------------- data-fix regressions
@needs_gold
def test_retired_hurt_is_not_a_wicket() -> None:
    d = read_gold(ROOT, "fact_deliveries")
    retired = d[d["dismissal_type"] == "retired hurt"]
    assert len(retired) > 0
    assert not retired["is_wicket"].fillna(False).any()


@needs_gold
def test_2003_league_matches_have_a_pool() -> None:
    m = read_gold(ROOT, "fact_matches")
    league = m[(m["tournament_id"] == "ODI_M_2003") & m["stage"].isin(["Group Stage", "Super Six"])]
    assert len(league) == 51 and league["group_name"].notna().all()
    assert set(league["group_name"]) == {"Pool A", "Pool B", "Super Sixes"}
    # Pool matches are between two teams of the same pool (pools are disjoint).
    st = read_gold(ROOT, "fact_tournament_standings")
    pools = st[st["group_name"].isin(["Pool A", "Pool B"]) & (st["tournament_id"] == "ODI_M_2003")]
    members = pools.groupby("group_name")["team_id"].agg(set).to_dict()
    for r in league[league["group_name"].isin(members)].itertuples():
        assert {r.team1_id, r.team2_id} <= members[r.group_name]


@needs_gold
def test_standings_have_single_unambiguous_team_name() -> None:
    cols = read_gold(ROOT, "fact_tournament_standings").columns
    assert "team_name" in cols and not {"team_name_x", "team_name_y"} & set(cols)
