# ruff: noqa: E501
"""Stage 15: orchestration logic (selection, dependencies, fail-fast, gates) with fake commands."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pandas as pd
import pytest
from src.pipeline import lakehouse_pipeline as lp


def fake_runner(fail: set[str] = frozenset(), outputs: dict[str, str] | None = None):
    calls = []

    def run(cmd, timeout):
        key = next((s.name for s in lp.STEPS if tuple(cmd) == s.cmd), "?")
        calls.append(key)
        if key in fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="boom\nsecond line")
        return SimpleNamespace(
            returncode=0, stdout=(outputs or {}).get(key, _default_out(key)), stderr=""
        )

    run.calls = calls
    return run


def _default_out(key: str) -> str:
    return {
        "verify_bronze": "bronze intact",
        "warehouse": "postgres row counts match gold",
        "quality_gold": "could not run: 0",
    }.get(key, "")


@pytest.fixture(autouse=True)
def no_quality_file(monkeypatch):
    monkeypatch.setitem(lp.GATES, "quality_gate", lambda out: (True, "stubbed"))


def test_dependency_graph_is_valid_and_ordered() -> None:
    names = lp.ORDER
    assert len(names) == len(set(names))
    for s in lp.STEPS:
        for d in s.depends_on:
            assert d in lp.BY_NAME and names.index(d) < names.index(s.name), (s.name, d)
        if s.gate:
            assert s.gate in lp.GATES


def test_default_selection_excludes_optional_synthetic() -> None:
    assert "synthetic" not in [s.name for s in lp.select_steps()]
    assert "synthetic" in [s.name for s in lp.select_steps(with_optional=["synthetic"])]


def test_selection_slices_and_validates() -> None:
    assert [s.name for s in lp.select_steps(start="warehouse", stop="dbt")] == [
        "warehouse",
        "quality_gold",
        "dbt",
    ]
    assert [s.name for s in lp.select_steps(only=["stats", "train"])] == ["train", "stats"] or {
        s.name for s in lp.select_steps(only=["stats", "train"])
    } == {"stats", "train"}
    assert "gold" not in [s.name for s in lp.select_steps(skip=["gold"])]
    with pytest.raises(ValueError, match="unknown step"):
        lp.select_steps(only=["nope"])


def test_full_success_runs_everything_in_order(tmp_path) -> None:
    run = fake_runner()
    steps = lp.select_steps()
    res = lp.run_pipeline(steps, runner=run, out_json=tmp_path / "r.json")
    assert [r.status for r in res] == ["ok"] * len(steps) and run.calls == [s.name for s in steps]
    rec = json.loads((tmp_path / "r.json").read_text())
    assert rec["success"] is True and len(rec["steps"]) == len(steps)


def test_failure_stops_the_run_and_marks_the_rest_skipped(tmp_path) -> None:
    run = fake_runner(fail={"silver"})
    res = lp.run_pipeline(lp.select_steps(), runner=run, out_json=tmp_path / "r.json")
    by = {r.name: r for r in res}
    assert (
        by["bronze"].status == "ok"
        and by["silver"].status == "failed"
        and "boom" in by["silver"].message
    )
    assert all(r.status == "skipped" for r in res if r.name not in ("bronze", "silver"))
    assert run.calls == ["bronze", "silver"]  # nothing ran after the failure
    assert json.loads((tmp_path / "r.json").read_text())["success"] is False


def test_gate_failure_is_a_failure_even_when_command_exits_zero(tmp_path) -> None:
    run = fake_runner(outputs={"verify_bronze": "something else"})
    res = lp.run_pipeline(
        lp.select_steps(stop="warehouse"), runner=run, out_json=tmp_path / "r.json"
    )
    by = {r.name: r for r in res}
    assert by["verify_bronze"].status == "gate_failed" and by["warehouse"].status == "skipped"


def test_dependency_outside_selection_does_not_block(tmp_path) -> None:
    run = fake_runner()
    res = lp.run_pipeline(lp.select_steps(only=["stats"]), runner=run, out_json=tmp_path / "r.json")
    assert [r.status for r in res] == ["ok"]


def test_dry_run_executes_nothing(tmp_path) -> None:
    run = fake_runner()
    res = lp.run_pipeline(lp.select_steps(), dry_run=True, runner=run, out_json=tmp_path / "r.json")
    assert run.calls == [] and all(r.status == "dry_run" for r in res)


def test_timeout_and_missing_command_are_reported(tmp_path) -> None:
    def boom(cmd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    def missing(cmd, timeout):
        raise FileNotFoundError("dbt")

    step = lp.BY_NAME["bronze"]
    assert "timed out" in lp.run_step(step, tmp_path, boom).message
    assert "not found" in lp.run_step(step, tmp_path, missing).message


def test_quality_gate_rules() -> None:
    def rows(rule, failed, sev="critical"):
        return {"rule_id": rule, "severity": sev, "failed": failed, "total": 100}

    ok = pd.DataFrame(
        [
            rows("gold.innings_wickets_match_deliveries", 1),
            rows("gold.ball_by_ball_available", 164, "minor"),
        ]
    )
    assert lp.evaluate_quality(ok)[0] is True
    worse = pd.DataFrame([rows("gold.innings_wickets_match_deliveries", 2)])
    assert lp.evaluate_quality(worse)[0] is False  # residual grew
    new = pd.DataFrame([rows("gold.match_has_result", 1)])
    ok2, msg = lp.evaluate_quality(new)
    assert ok2 is False and "match_has_result" in msg
    assert lp.evaluate_quality(pd.DataFrame([rows("gold.x", 0)]))[0] is True


def test_gate_messages() -> None:
    assert lp.gate_bronze_intact("bronze intact")[0] and not lp.gate_bronze_intact("differs")[0]
    assert (
        lp.gate_row_counts("postgres row counts match gold")[0]
        and not lp.gate_row_counts("MISMATCH")[0]
    )
