"""Data-quality framework: rule engine, scoring maths, persistence (synthetic data only)."""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from src.validation.rules import Rule, validate_rule_ids
from src.validation.validate_data_quality import (
    collect_rules,
    dataset_scores,
    persist_results,
    run_all,
    tournament_scores,
)


@pytest.fixture()
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "create table matches (match_id text, tournament_id text, team1_id text, team2_id text, winner_id text)"
            )
        )
        conn.execute(
            text(
                "insert into matches values ('1','T1','a','b','a'), ('2','T1','a','b','c'), "
                "('3','T1','a','b',null), ('4','T2','a','b','b'), ('5','T2','a','b','z')"
            )
        )
    return engine


def _winner_rule() -> Rule:
    return Rule(
        "t.winner_is_participant",
        "matches",
        "referential_integrity",
        "critical",
        "winner is a participant",
        "matches m",
        "m.winner_id not in (m.team1_id, m.team2_id)",
        where="m.winner_id is not null",
        key="m.match_id",
    )


def test_rule_counts_failures_per_tournament(sqlite_engine) -> None:
    results, errors = run_all(sqlite_engine, [_winner_rule()])
    assert errors.empty
    by_t = results.set_index("tournament_id")
    assert (by_t.loc["T1", "total"], by_t.loc["T1", "failed"]) == (
        2,
        1,
    )  # null winner excluded from total
    assert (by_t.loc["T2", "total"], by_t.loc["T2", "failed"]) == (2, 1)
    # examples are the first failing rows of the whole rule (not per tournament)
    assert set(by_t.loc["T1", "examples"].split(", ")) == {"2", "5"}
    assert by_t.loc["T1", "pass_rate"] == pytest.approx(0.5)


def test_broken_rule_is_reported_not_hidden(sqlite_engine) -> None:
    bad = Rule("t.broken", "matches", "validity", "major", "x", "no_such_table n", "n.x = 1")
    results, errors = run_all(sqlite_engine, [bad, _winner_rule()])
    assert errors["rule_id"].tolist() == ["t.broken"]
    assert set(results["rule_id"]) == {"t.winner_is_participant"}


def test_rule_without_failures_has_full_pass_rate(sqlite_engine) -> None:
    ok = Rule("t.ok", "matches", "validity", "minor", "x", "matches m", "m.team1_id = m.team2_id")
    results, _ = run_all(sqlite_engine, [ok])
    assert results["failed"].sum() == 0 and (results["pass_rate"] == 1.0).all()


def test_validate_rule_ids_rejects_duplicates_and_bad_values() -> None:
    r = _winner_rule()
    with pytest.raises(ValueError, match="duplicate"):
        validate_rule_ids([r, r])
    with pytest.raises(ValueError, match="dimension"):
        validate_rule_ids([Rule("x", "d", "nope", "major", "d", "t", "1=1")])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="severity"):
        validate_rule_ids([Rule("x", "d", "validity", "huge", "d", "t", "1=1")])  # type: ignore[arg-type]


def test_all_shipped_rules_are_well_formed_and_unique() -> None:
    rules = collect_rules(None)
    assert len(rules) >= 45
    assert {r.dimension for r in rules} == {
        "completeness",
        "uniqueness",
        "validity",
        "referential_integrity",
        "consistency",
        "historical_coverage",
    }
    for r in rules:
        assert r.count_sql().lstrip().lower().startswith("select")


def _frame(rows):
    df = pd.DataFrame(
        rows,
        columns=["rule_id", "dataset", "dimension", "severity", "tournament_id", "total", "failed"],
    )
    return df


def test_scoring_uses_severity_weights_and_dimension_means() -> None:
    results = _frame(
        [
            # validity: critical rule 100% pass (w3), minor rule 50% pass (w1) -> (3*1 + 1*0.5)/4 = 87.5
            ("r1", "matches", "validity", "critical", "T1", 100, 0),
            ("r2", "matches", "validity", "minor", "T1", 10, 5),
            # completeness: one major rule, 80% pass -> 80
            ("r3", "matches", "completeness", "major", "T1", 10, 2),
            # a rule with nothing to check is ignored
            ("r4", "matches", "consistency", "major", "T1", 0, 0),
        ]
    )
    s = tournament_scores(results).set_index("tournament_id").loc["T1"]
    assert s["validity"] == pytest.approx(87.5)
    assert s["completeness"] == pytest.approx(80.0)
    assert pd.isna(s["consistency"])
    assert s["overall"] == pytest.approx((87.5 + 80.0) / 2, abs=0.06)  # output is rounded to 1 dp
    assert s["critical_rules_failing"] == 0
    assert s["rules_failing"] == 2


def test_dataset_scores_pool_rows_before_scoring() -> None:
    results = _frame(
        [
            ("r1", "d", "validity", "major", "T1", 1000, 100),  # 10% fail on a big tournament
            ("r1", "d", "validity", "major", "T2", 10, 0),
        ]
    )
    s = dataset_scores(results).set_index("dataset").loc["d"]
    assert s["validity"] == pytest.approx(100 * (1 - 100 / 1010), abs=0.1)


def test_persist_replaces_only_framework_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "create table data_quality_results (entity_type text, entity_id text, tournament_id text, "
                "check_name text, severity text, status text, message text, details_json text)"
            )
        )
        conn.execute(
            text(
                "insert into data_quality_results (entity_type, check_name, severity, status) "
                "values ('match', 'legacy', 'warning', 'fail')"
            )
        )
    results = _frame([("r1", "matches", "validity", "critical", "(global)", 10, 1)])
    results["description"] = "d"
    results["examples"] = "x"
    results["pass_rate"] = 0.9
    assert persist_results(engine, results) == 1
    assert persist_results(engine, results) == 1  # idempotent: replaces, never duplicates
    with engine.connect() as conn:
        kinds = dict(
            conn.execute(
                text("select entity_type, count(*) from data_quality_results group by 1")
            ).fetchall()
        )
        row = conn.execute(
            text(
                "select tournament_id, severity, status from data_quality_results where entity_type='dq_rule'"
            )
        ).one()
    assert kinds == {"match": 1, "dq_rule": 1}
    assert tuple(row) == (None, "error", "fail")  # (global) -> NULL tournament; critical -> error


def _postgres_available() -> bool:
    try:
        from src.database.connection import check_connection, reset_engine_cache

        reset_engine_cache()
        return check_connection()
    except Exception:
        return False


@pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL is not reachable")
def test_every_rule_executes_against_postgres() -> None:
    from src.database.connection import get_engine

    engine = get_engine()
    results, errors = run_all(engine, collect_rules(engine))
    assert errors.empty, errors.to_string()
    assert results["rule_id"].nunique() >= 100
    assert (results["failed"] <= results["total"]).all()
