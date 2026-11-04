"""Run every data-quality rule, score the results, persist and report (Stage 3).

Scoring method (also written into the report):

* Each rule yields ``total`` rows checked and ``failed`` rows violating it, per tournament.
* ``pass_rate = 1 - failed / total`` (rules with no rows to check are skipped).
* A dimension score is the severity-weighted mean pass rate of the rules in that dimension
  (critical = 3, major = 2, minor = 1), so a cosmetic gap cannot outweigh a broken total.
* The overall score is the plain mean of the available dimension scores (equal dimension weights).
  It is a summary; the dimension scores and failing rules are the actual findings.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.validation import (
    validate_deliveries,
    validate_innings,
    validate_matches,
    validate_players,
    validate_relationships,
    validate_teams,
    validate_tournaments,
)
from src.validation.rules import DIMENSIONS, GLOBAL, SEVERITY_WEIGHT, Rule, validate_rule_ids

logger = logging.getLogger(__name__)

STATIC_MODULES = (
    validate_tournaments,
    validate_matches,
    validate_innings,
    validate_deliveries,
    validate_players,
    validate_teams,
    validate_relationships,
)
PERSIST_ENTITY = "dq_rule"
SEVERITY_TO_DB = {"critical": "error", "major": "warning", "minor": "info"}


def collect_rules(engine: Engine | None = None) -> list[Rule]:
    rules: list[Rule] = []
    for module in STATIC_MODULES:
        rules.extend(module.RULES)
    if engine is not None:
        rules.extend(validate_relationships.declared_fk_rules(engine))
    validate_rule_ids(rules)
    return rules


# --------------------------------------------------------------------------- execution
def run_rule(engine: Engine, rule: Rule) -> tuple[list[dict[str, Any]], str, float]:
    """Return (per-tournament rows, example text, seconds). Raises on SQL errors."""
    started = time.perf_counter()
    with engine.connect() as conn:
        rows = conn.execute(text(rule.count_sql())).fetchall()
        examples = ""
        sql = rule.example_sql()
        if sql and any(r[2] for r in rows):
            try:
                examples = ", ".join(str(r[0]) for r in conn.execute(text(sql)).fetchall())
            except Exception:  # noqa: BLE001 - examples are a nicety, never fail a rule for them
                examples = ""
    out = [
        {"tournament_id": r[0] or GLOBAL, "total": int(r[1]), "failed": int(r[2] or 0)}
        for r in rows
    ]
    return out, examples, time.perf_counter() - started


def run_all(engine: Engine, rules: list[Rule] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Execute all rules. Returns (results, errors). A broken rule is reported, never hidden."""
    rules = rules if rules is not None else collect_rules(engine)
    result_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for rule in rules:
        try:
            rows, examples, secs = run_rule(engine, rule)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {"rule_id": rule.rule_id, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            )
            logger.warning("rule %s failed to run: %s", rule.rule_id, exc)
            continue
        for r in rows:
            result_rows.append(
                {
                    "rule_id": rule.rule_id,
                    "dataset": rule.dataset,
                    "dimension": rule.dimension,
                    "severity": rule.severity,
                    "description": rule.description,
                    "tournament_id": r["tournament_id"],
                    "total": r["total"],
                    "failed": r["failed"],
                    "examples": examples if r["failed"] else "",
                    "note": rule.note,
                    "seconds": round(secs, 3),
                }
            )
    results = pd.DataFrame(result_rows)
    if not results.empty:
        results["pass_rate"] = (
            1 - results["failed"] / results["total"].where(results["total"] > 0)
        ).round(6)
    return results, pd.DataFrame(errors, columns=["rule_id", "error"])


# --------------------------------------------------------------------------- scoring
def _weighted_dimension_scores(rule_rows: pd.DataFrame, group: str) -> pd.DataFrame:
    rows = rule_rows[rule_rows["total"] > 0].copy()
    rows["w"] = rows["severity"].map(SEVERITY_WEIGHT)
    rows["wp"] = rows["w"] * (1 - rows["failed"] / rows["total"])
    agg = rows.groupby([group, "dimension"]).agg(wp=("wp", "sum"), w=("w", "sum"))
    scores = (100 * agg["wp"] / agg["w"]).unstack("dimension").reindex(columns=list(DIMENSIONS))
    scores["overall"] = scores.mean(axis=1, skipna=True)
    extra = rows.groupby(group).agg(
        rules_evaluated=("rule_id", "nunique"),
        rules_failing=("failed", lambda s: int((s > 0).sum())),
    )
    critical = (
        rows[(rows["severity"] == "critical") & (rows["failed"] > 0)]
        .groupby(group)["rule_id"]
        .nunique()
    )
    out = scores.join(extra)
    out["critical_rules_failing"] = critical.reindex(out.index).fillna(0).astype(int)
    return out.round(1).reset_index()


def tournament_scores(results: pd.DataFrame) -> pd.DataFrame:
    return _weighted_dimension_scores(results, "tournament_id")


def dataset_scores(results: pd.DataFrame) -> pd.DataFrame:
    """Pool each rule across tournaments first so large tournaments do not dominate by row count."""
    pooled = results.groupby(["dataset", "rule_id", "dimension", "severity"], as_index=False)[
        ["total", "failed"]
    ].sum()
    return _weighted_dimension_scores(pooled, "dataset")


# --------------------------------------------------------------------------- persistence
def persist_results(
    engine: Engine, results: pd.DataFrame, entity_type: str = PERSIST_ENTITY
) -> int:
    """Replace this framework's rows in data_quality_results (touches only entity_type='dq_rule')."""
    now = datetime.now(UTC).isoformat()
    payload = []
    for r in results.itertuples():
        details = {
            "dimension": r.dimension,
            "severity": r.severity,
            "dataset": r.dataset,
            "total": int(r.total),
            "failed": int(r.failed),
            "pass_rate": None if pd.isna(r.pass_rate) else float(r.pass_rate),
            "examples": r.examples,
            "run_at": now,
        }
        payload.append(
            {
                "entity_type": entity_type,
                "entity_id": r.rule_id,
                "tournament_id": None if r.tournament_id == GLOBAL else r.tournament_id,
                "check_name": r.rule_id,
                "severity": SEVERITY_TO_DB[r.severity],
                "status": "pass" if r.failed == 0 else "fail",
                "message": f"{r.failed} of {r.total} rows failed: {r.description}",
                "details_json": json.dumps(details),
            }
        )
    with engine.begin() as conn:
        conn.execute(
            text("delete from data_quality_results where entity_type = :e"), {"e": entity_type}
        )
        if payload:
            conn.execute(
                text(
                    "insert into data_quality_results (entity_type, entity_id, tournament_id, check_name, "
                    "severity, status, message, details_json) values (:entity_type, :entity_id, :tournament_id, "
                    ":check_name, :severity, :status, :message, :details_json)"
                ),
                payload,
            )
    return len(payload)


# --------------------------------------------------------------------------- reporting
def _md(df: pd.DataFrame, max_rows: int = 80) -> str:
    if df.empty:
        return "_none_\n"
    d = df.head(max_rows).astype(object).where(df.head(max_rows).notna(), "")
    cols = list(d.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in d.iterrows():
        lines.append(
            "| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ") for c in cols) + " |"
        )
    return "\n".join(lines) + "\n"


def write_reports(
    results: pd.DataFrame,
    errors: pd.DataFrame,
    rules: list[Rule],
    out_dir: Path,
    *,
    persisted: int | None = None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sub = out_dir / "data_quality"
    sub.mkdir(exist_ok=True)

    t_scores = tournament_scores(results)
    d_scores = dataset_scores(results)
    failing = results[results["failed"] > 0].copy()
    failing["sev_rank"] = failing["severity"].map({"critical": 0, "major": 1, "minor": 2})
    pooled = failing.groupby(
        ["rule_id", "dataset", "dimension", "severity", "description", "note"], as_index=False
    ).agg(
        failed=("failed", "sum"),
        total=("total", "sum"),
        tournaments_affected=("tournament_id", "nunique"),
        examples=("examples", "first"),
    )
    all_pooled = (
        results.groupby("rule_id", as_index=False)[["total"]]
        .sum()
        .rename(columns={"total": "total_all"})
    )
    pooled = pooled.merge(all_pooled, on="rule_id")
    pooled["fail_pct"] = (100 * pooled["failed"] / pooled["total_all"]).round(2)
    pooled["sev_rank"] = pooled["severity"].map({"critical": 0, "major": 1, "minor": 2})
    pooled = pooled.sort_values(["sev_rank", "fail_pct"], ascending=[True, False]).drop(
        columns=["sev_rank", "total"]
    )

    catalog = pd.DataFrame(
        [
            {
                "rule_id": r.rule_id,
                "dataset": r.dataset,
                "dimension": r.dimension,
                "severity": r.severity,
                "description": r.description,
                "note": r.note,
            }
            for r in rules
        ]
    )
    results.to_csv(sub / "rule_results.csv", index=False)
    t_scores.to_csv(sub / "tournament_scores.csv", index=False)
    d_scores.to_csv(sub / "dataset_scores.csv", index=False)
    catalog.to_csv(sub / "rule_catalog.csv", index=False)
    if len(errors):
        errors.to_csv(sub / "rule_errors.csv", index=False)

    n_rules = results["rule_id"].nunique()
    clean = n_rules - pooled["rule_id"].nunique()
    crit = pooled[pooled["severity"] == "critical"]
    tour = t_scores[t_scores["tournament_id"] != GLOBAL].sort_values("overall")
    worst, best = tour.iloc[0], tour.iloc[-1]
    show_cols = ["tournament_id", *DIMENSIONS, "overall", "critical_rules_failing"]
    pretty = {
        c: c.replace("referential_integrity", "ref_integrity").replace(
            "historical_coverage", "coverage"
        )
        for c in show_cols
    }

    dim_cols = list(DIMENSIONS)
    weakest_dim = worst[dim_cols].astype(float).idxmin()
    weakest_text = (
        f"The lowest tournament's weakest dimension is **{weakest_dim}** "
        f"({worst[weakest_dim]:.1f}), against {tour[weakest_dim].median():.1f} as the median across tournaments."
    )
    dim_means = tour[dim_cols].astype(float).mean().sort_values()
    low_dims = ", ".join(f"{d} ({v:.1f})" for d, v in dim_means.head(2).items())
    high_dims = ", ".join(f"{d} ({v:.1f})" for d, v in dim_means.tail(2).items())
    top_failures = ", ".join(
        f"`{r.rule_id}` ({r.fail_pct:g}%)"
        for r in pooled[pooled["severity"] != "minor"].head(4).itertuples()
    )
    conclusion = (
        f"Averaged over tournaments, the weakest dimensions are {low_dims}; the strongest are {high_dims}. "
        f"The most material failing rules (critical/major, by failure rate) are {top_failures or 'none'}. "
        "Dimension scores near 100 mean the rules found few defects, not that the data is proven correct: "
        "rules only detect what they test (see limitations)."
    )

    lines = [
        "# Data Quality Report",
        "",
        f"_Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by "
        "`scripts/run_data_quality.py` from the live PostgreSQL data. All figures are computed; re-run to refresh._",
        "",
        "## 1. Research objective",
        "",
        "Measure how trustworthy each part of the collected World Cup data is, for every tournament and dataset, "
        "using explicit, reproducible rules. The goal is to locate defects precisely, not to produce a single grade.",
        "",
        "## 2. Dataset used",
        "",
        f"The PostgreSQL analytical database (tournaments, matches, innings, deliveries, scorecards, players, teams, "
        f"standings, squads). **{n_rules} rules** ran over {results['total'].sum():,} row checks.",
        "",
        "## 3. Methodology",
        "",
        "Every rule counts `failed` rows out of `total` rows checked, per tournament. `pass rate = 1 - failed / total`.",
        "",
        "| Dimension | What it measures |",
        "|---|---|",
        "| completeness | required values are present |",
        "| uniqueness | no duplicate entities or keys |",
        "| validity | values are in legal ranges / sets |",
        "| referential_integrity | references point at the right rows (declared FKs and cricket logic) |",
        "| consistency | related values agree (scorecard vs ball-by-ball vs result text) |",
        "| historical_coverage | data that should exist for a played match / tournament does exist |",
        "",
        "- **Dimension score** = severity-weighted mean pass rate of its rules (critical x3, major x2, minor x1).",
        "- **Overall** = plain mean of the available dimension scores (equal weights). It is only a summary.",
        "- Rules pooled **per rule** before dataset scores, so large tournaments do not dominate by row count.",
        "- `(global)` rows are checks without a tournament (e.g. declared foreign keys).",
        "",
        "## 4. Data limitations",
        "",
        "- Scores are only comparable within this rule set; adding rules changes them.",
        "- Coverage rules compare against what *should* exist, not what any source can provide. Ball-by-ball for "
        "T20 2007-2012 is unavailable from every free source checked, so that is a coverage gap, not a defect.",
        "- Some rules can raise false positives (see the 'note' column in the failing-rule table).",
        "- Rules cannot detect errors that are internally consistent (e.g. a wrong but self-consistent score).",
        "",
        "## 5. Results",
        "",
        "### Scores by tournament (0-100)",
        "",
        _md(tour[show_cols].rename(columns=pretty)),
        "### Scores by dataset (0-100)",
        "",
        _md(
            d_scores[
                [
                    "dataset",
                    *DIMENSIONS,
                    "overall",
                    "rules_evaluated",
                    "rules_failing",
                    "critical_rules_failing",
                ]
            ].rename(columns=pretty)
        ),
        f"### Failing rules ({len(pooled)} of {n_rules}; {clean} rules passed on every row)",
        "",
        _md(
            pooled[
                [
                    "severity",
                    "rule_id",
                    "failed",
                    "total_all",
                    "fail_pct",
                    "tournaments_affected",
                    "examples",
                    "note",
                ]
            ],
            60,
        ),
    ]
    if len(errors):
        lines += ["### Rules that could not run", "", _md(errors), ""]
    lines += [
        "## 6. Interpretation",
        "",
        f"- **{len(crit)} critical rules** have failures"
        + (": " + ", ".join(f"`{r}`" for r in crit["rule_id"]) if len(crit) else "")
        + ".",
        f"- Highest overall score: **{best['tournament_id']} ({best['overall']})**; lowest: "
        f"**{worst['tournament_id']} ({worst['overall']})**. {weakest_text}",
        f"- Across tournaments the validity score ranges {tour['validity'].min():.1f}-{tour['validity'].max():.1f} and "
        f"consistency {tour['consistency'].min():.1f}-{tour['consistency'].max():.1f}; coverage ranges "
        f"{tour['historical_coverage'].min():.1f}-{tour['historical_coverage'].max():.1f} and completeness "
        f"{tour['completeness'].min():.1f}-{tour['completeness'].max():.1f}.",
        "- Failures marked with a `note` may be legitimate cricket events or source limitations; treat them as "
        "review items rather than proven errors.",
        "",
        "## 7. Conclusion",
        "",
        conclusion,
        "",
        "## 8. Reproduce",
        "",
        "```powershell",
        "python scripts/run_data_quality.py            # reports only",
        "python scripts/run_data_quality.py --persist  # also refresh data_quality_results",
        "```",
        "",
        "Detail files: `reports/data_quality/` (rule_results, tournament_scores, dataset_scores, rule_catalog)."
        + (
            f" {persisted} rows written to `data_quality_results`." if persisted is not None else ""
        ),
        "",
    ]
    report = out_dir / "data_quality_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return {"report": report, "dir": sub}
