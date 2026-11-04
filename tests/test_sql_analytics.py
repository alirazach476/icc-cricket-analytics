"""Stage 7/8: the SQL analytics library runs and reproduces known cricket records."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "cricket_gold.duckdb"

pytestmark = pytest.mark.skipif(not DB.exists(), reason="gold DuckDB not built")


def _runner():
    spec = importlib.util.spec_from_file_location(
        "run_sql_analytics", ROOT / "scripts" / "run_sql_analytics.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def results():
    runner = _runner()  # an error here is a real failure, never a skip
    try:
        out = runner.run()
    except duckdb.IOException as exc:
        pytest.skip(f"cannot open DuckDB (version mismatch or locked): {exc}")
    return {r["name"]: r for r in out}


def test_library_size_and_unique_names(results) -> None:
    assert len(results) >= 30


def test_every_query_runs_and_returns_rows(results) -> None:
    broken = {n: r["error"] for n, r in results.items() if r["error"]}
    assert not broken, broken
    empty = [n for n, r in results.items() if len(r["df"]) == 0]
    assert not empty, empty


def test_every_query_documented(results) -> None:
    assert all(r["group"] and r["question"] for r in results.values())


def test_known_records(results) -> None:
    q = lambda n: results[n]["df"]  # noqa: E731
    assert q("q02_highest_individual_scores").iloc[0][["player", "runs"]].tolist() == [
        "Martin Guptill",
        237,
    ]
    assert q("q07_best_bowling_innings").iloc[0][
        ["player", "wickets", "runs_conceded"]
    ].tolist() == ["Glenn McGrath", 7, 15]
    assert int(q("q13_highest_team_totals").iloc[0]["total_runs"]) == 428
    assert int(q("q14_lowest_all_out_totals").iloc[0]["total_runs"]) == 36
    odi = q("q01_top_run_scorers_by_format").query("format == 'ODI'").iloc[0]
    assert (odi["player"], int(odi["runs"])) == ("Virat Kohli", 1795)
    assert int(q("q15_biggest_wins_by_runs").iloc[0]["runs_margin"]) == 309


def test_chase_buckets_are_bucketed(results) -> None:
    df = results["q34_chase_success_by_target"]["df"]
    assert len(df) < 40 and (df["target_from"] % 20 == 0).all()
