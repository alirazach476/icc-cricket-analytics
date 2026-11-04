# ruff: noqa: E501
"""Stage 15: orchestration of the full analytics flow (bronze -> gold -> warehouse -> analytics -> ML -> report).

Properties
* Declarative steps with dependencies; `--from/--to/--only/--skip` select a slice, and a step is only run if
  everything it depends on in the *selection* succeeded (fail-fast: the first failure stops the run).
* Each step runs as a subprocess with its output saved to logs/pipeline/<run_id>/<step>.log.
* Quality gates are separate from "the command exited 0": e.g. the gold data-quality gate fails the run if a
  *critical* rule fails beyond the documented, explained residuals.
* Every step is idempotent (bronze batches are content-hashed, loads are upserts), so the whole pipeline can be
  re-run safely at any time.
* A machine-readable record is written to reports/pipeline_run.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

# Critical gold rules that are allowed to have a documented, bounded residual (see reports/gold).
ALLOWED_CRITICAL_RESIDUALS = {"gold.innings_wickets_match_deliveries": 1}


@dataclass(frozen=True)
class Step:
    name: str
    cmd: tuple[str, ...]
    description: str
    depends_on: tuple[str, ...] = ()
    optional: bool = False  # only runs when explicitly requested (--with)
    gate: str | None = None  # name of a gate function run after the command succeeds
    timeout: int = 1800


def _script(name: str, *args: str) -> tuple[str, ...]:
    return (PY, str(ROOT / "scripts" / name), *args)


def _dbt(*args: str) -> tuple[str, ...]:
    return (
        "dbt",
        *args,
        "--project-dir",
        str(ROOT / "dbt_gold"),
        "--profiles-dir",
        str(ROOT / "dbt_gold"),
    )


STEPS: tuple[Step, ...] = (
    Step(
        "bronze",
        _script("build_lakehouse.py", "--layer", "bronze"),
        "Snapshot raw collected files (immutable, content-hashed)",
    ),
    Step(
        "silver",
        _script("build_lakehouse.py", "--layer", "silver"),
        "Clean and conform (identities, teams, stages, results)",
        ("bronze",),
    ),
    Step(
        "gold",
        _script("build_lakehouse.py", "--layer", "gold"),
        "Dimensions, facts and marts",
        ("silver",),
    ),
    Step(
        "verify_bronze",
        _script("build_lakehouse.py", "--verify"),
        "Re-hash bronze against its manifest",
        ("gold",),
        gate="bronze_intact",
    ),
    Step(
        "synthetic",
        _script("generate_synthetic_conditions.py"),
        "SYNTHETIC pitch/weather/day-night placeholders (optional)",
        ("gold",),
        optional=True,
    ),
    Step(
        "warehouse",
        _script("load_warehouse.py"),
        "Upsert gold into Postgres (analytics) and rebuild DuckDB",
        ("gold",),
        gate="row_counts",
    ),
    Step(
        "quality_gold",
        _script("run_data_quality.py", "--layer", "gold", "--persist"),
        "Data-quality rules on the resolved data",
        ("warehouse",),
        gate="quality_gate",
    ),
    Step("dbt", _dbt("build"), "dbt models and tests on gold", ("warehouse",)),
    Step(
        "sql_analytics", _script("run_sql_analytics.py"), "Run the SQL analytics library", ("dbt",)
    ),
    Step(
        "stats",
        _script("run_statistical_tests.py"),
        "Hypothesis tests with multiple-testing correction",
        ("warehouse",),
    ),
    Step("notebooks", _script("build_notebooks.py"), "Execute the EDA notebooks", ("dbt",)),
    Step("features", _script("build_features.py"), "Leakage-safe feature table", ("warehouse",)),
    Step(
        "train",
        _script("train_models.py"),
        "Expanding-window evaluation and final models",
        ("features",),
    ),
    Step(
        "explain",
        _script("explain_models.py"),
        "Permutation importance, SHAP, ablation",
        ("train",),
    ),
    Step(
        "innings_projection",
        _script("train_innings_projection.py"),
        "Live first-innings score projection (Model 2)",
        ("features",),
    ),
    Step(
        "player_models",
        _script("run_player_models.py"),
        "Consistency, role clustering and batting regression (Models 3-5)",
        ("features",),
    ),
    Step(
        "report",
        _script("build_report.py"),
        "Executive report built from the outputs above",
        ("quality_gold", "sql_analytics", "stats", "train", "explain"),
    ),
    Step(
        "spec_reports",
        _script("build_spec_reports.py"),
        "The six written reports (ten required sections each) and their figures",
        ("quality_gold", "sql_analytics", "stats", "train", "innings_projection", "player_models", "explain"),
    ),
    Step("docs", _script("build_docs.py"), "Data dictionary from the live schema", ("warehouse",)),
    Step(
        "competitions",
        _script("run_competitions.py"),
        "Champions Trophy and World Test Championship finals (Cricsheet -> silver -> gold -> DuckDB)",
        ("gold",),
    ),
)
BY_NAME = {s.name: s for s in STEPS}
ORDER = [s.name for s in STEPS]


# --------------------------------------------------------------------------- gates
def gate_bronze_intact(output: str) -> tuple[bool, str]:
    ok = "bronze intact" in output
    return (
        ok,
        "bronze matches its manifest"
        if ok
        else "bronze verification did not report 'bronze intact'",
    )


def gate_row_counts(output: str) -> tuple[bool, str]:
    ok = "postgres row counts match gold" in output
    return ok, "Postgres row counts match gold" if ok else "Postgres row counts differ from gold"


def gate_quality(output: str, results_csv: Path | None = None) -> tuple[bool, str]:
    """Fail on any critical rule failure beyond the documented residuals, or any rule that could not run."""
    path = results_csv or ROOT / "reports" / "gold" / "data_quality" / "rule_results.csv"
    if "could not run: 0" not in output:
        return False, "some quality rules could not run"
    return evaluate_quality(pd.read_csv(path))


def evaluate_quality(results: pd.DataFrame) -> tuple[bool, str]:
    crit = results[results["severity"] == "critical"].groupby("rule_id")["failed"].sum()
    bad = {r: int(n) for r, n in crit.items() if n > ALLOWED_CRITICAL_RESIDUALS.get(r, 0)}
    if bad:
        return False, f"critical rules failing beyond allowed residuals: {bad}"
    return (
        True,
        f"no critical failures beyond documented residuals ({int((crit > 0).sum())} within allowance)",
    )


GATES: dict[str, Callable[[str], tuple[bool, str]]] = {
    "bronze_intact": gate_bronze_intact,
    "row_counts": gate_row_counts,
    "quality_gate": gate_quality,
}


# --------------------------------------------------------------------------- selection and execution
def select_steps(
    only: list[str] | None = None,
    start: str | None = None,
    stop: str | None = None,
    skip: list[str] | None = None,
    with_optional: list[str] | None = None,
) -> list[Step]:
    names = set(ORDER)
    for group in (
        only or [],
        skip or [],
        with_optional or [],
        [start] if start else [],
        [stop] if stop else [],
    ):
        unknown = set(group) - names
        if unknown:
            raise ValueError(f"unknown step(s): {sorted(unknown)}; known: {ORDER}")
    chosen = [s for s in STEPS if not s.optional or s.name in (with_optional or [])]
    if only:
        chosen = [s for s in STEPS if s.name in only]
    if start:
        chosen = [s for s in chosen if ORDER.index(s.name) >= ORDER.index(start)]
    if stop:
        chosen = [s for s in chosen if ORDER.index(s.name) <= ORDER.index(stop)]
    return [s for s in chosen if s.name not in (skip or [])]


@dataclass
class StepResult:
    name: str
    status: str  # ok | failed | gate_failed | skipped | dry_run
    seconds: float = 0.0
    returncode: int | None = None
    message: str = ""
    log: str = ""
    extra: dict = field(default_factory=dict)


def run_step(step: Step, log_dir: Path, runner: Callable | None = None) -> StepResult:
    started = time.perf_counter()
    run = runner or (
        lambda cmd, timeout: subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    )
    try:
        proc = run(list(step.cmd), step.timeout)
    except subprocess.TimeoutExpired:
        return StepResult(
            step.name,
            "failed",
            time.perf_counter() - started,
            None,
            f"timed out after {step.timeout}s",
        )
    except FileNotFoundError as exc:
        return StepResult(
            step.name, "failed", time.perf_counter() - started, None, f"command not found: {exc}"
        )
    output = (proc.stdout or "") + (proc.stderr or "")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{step.name}.log"
    log_path.write_text(output, encoding="utf-8")
    secs = time.perf_counter() - started
    rel = str(log_path.relative_to(ROOT)) if log_path.is_relative_to(ROOT) else str(log_path)
    if proc.returncode != 0:
        tail = " | ".join(output.strip().splitlines()[-3:])
        return StepResult(step.name, "failed", secs, proc.returncode, tail[:300], rel)
    if step.gate:
        ok, msg = GATES[step.gate](output)
        return StepResult(step.name, "ok" if ok else "gate_failed", secs, 0, msg, rel)
    return StepResult(step.name, "ok", secs, 0, "", rel)


def run_pipeline(
    steps: list[Step],
    dry_run: bool = False,
    runner: Callable | None = None,
    out_json: Path | None = None,
) -> list[StepResult]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_dir = ROOT / "logs" / "pipeline" / run_id
    results: list[StepResult] = []
    stopped = False
    selected = {s.name for s in steps}
    done_ok: set[str] = set()
    for step in steps:
        if dry_run:
            results.append(
                StepResult(
                    step.name,
                    "dry_run",
                    message=" ".join(Path(c).name if i < 2 else c for i, c in enumerate(step.cmd)),
                )
            )
            continue
        blockers = [d for d in step.depends_on if d in selected and d not in done_ok]
        if stopped or blockers:
            results.append(
                StepResult(
                    step.name,
                    "skipped",
                    message=f"not run: {'earlier failure' if stopped else 'dependency ' + ','.join(blockers) + ' did not succeed'}",
                )
            )
            continue
        res = run_step(step, log_dir, runner)
        results.append(res)
        if res.status == "ok":
            done_ok.add(step.name)
        else:
            stopped = True
    if out_json is not False:
        record = {
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(),
            "dry_run": dry_run,
            "success": all(r.status in ("ok", "dry_run") for r in results),
            "steps": [r.__dict__ for r in results],
        }
        target = out_json or ROOT / "reports" / "pipeline_run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return results
