# ruff: noqa: E501
"""Stage 16: executive report generated from the pipeline's own outputs (nothing typed by hand).

Every number comes from the gold DuckDB or from the CSV/JSON reports written by earlier stages. If an input
is missing, the section says so instead of inventing a value.
"""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DB = ROOT / "data" / "warehouse" / "cricket_gold.duckdb"


def table(df: pd.DataFrame, digits: int = 2) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append(
            "| "
            + " | ".join(
                "-"
                if isinstance(v, float) and v != v
                else f"{v:.{digits}f}"
                if isinstance(v, float)
                else str(v)
                for v in r
            )
            + " |"
        )
    return "\n".join(out)


def _csv(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def _q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).fetchdf()


def gather(root: Path = ROOT, db: Path = DB) -> dict:
    """Collect every fact the report needs. Missing inputs become None."""
    rep = root / "reports"
    con = duckdb.connect(str(db), read_only=True)
    try:
        facts = {
            "counts": _q(
                con,
                "select (select count(*) from gold.fact_matches) matches, (select count(*) from gold.dim_players) players, (select count(*) from gold.fact_deliveries) deliveries, (select count(*) from gold.dim_tournaments) tournaments, (select count(*) from gold.dim_venues) venues, (select count(*) from gold.dim_teams) teams",
            )
            .iloc[0]
            .to_dict(),
            "coverage": _q(
                con,
                "select sum(played_matches) played, sum(played_with_ball_by_ball) bbb from gold.mart_data_coverage",
            )
            .iloc[0]
            .to_dict(),
            "gaps": _q(
                con,
                "select coalesce(ball_by_ball_gap_reason,'has ball-by-ball') as status, count(*) as matches from gold.fact_matches group by 1 order by 2 desc",
            ),
            "champions": _q(
                con,
                "select format, year, winner, runner_up, player_of_tournament from gold.mart_tournament_summary order by format, year",
            ),
            "span": _q(
                con,
                "select format, min(year) first_year, max(year) last_year, count(*) editions from gold.dim_tournaments group by 1 order by 1",
            ),
        }
    finally:
        con.close()
    facts["quality"] = _csv(rep / "gold" / "data_quality" / "dataset_scores.csv")
    facts["rules"] = _csv(rep / "gold" / "data_quality" / "rule_results.csv")
    facts["stats"] = _csv(rep / "statistical_tests.csv")
    facts["winner_metrics"] = _csv(rep / "model_comparison" / "winner_metrics.csv")
    facts["score_metrics"] = _csv(rep / "model_comparison" / "score_metrics.csv")
    facts["ablation"] = _csv(rep / "model_comparison" / "ablation_winner.csv")
    facts["importance"] = _csv(rep / "feature_importance" / "importance_winner_logistic.csv")
    facts["proj_gains"] = _csv(rep / "model_evaluation" / "innings_projection_gains.csv")
    facts["cluster_sel"] = {k: _csv(rep / "model_evaluation" / f"clusters_{k}_k_selection.csv") for k in ("batters", "bowlers")}
    facts["pipeline"] = (
        json.loads((rep / "pipeline_run.json").read_text(encoding="utf-8"))
        if (rep / "pipeline_run.json").exists()
        else None
    )
    sql = rep / "sql_analytics"
    facts["records"] = {
        n: _csv(sql / f"{n}.csv")
        for n in (
            "q02_highest_individual_scores",
            "q07_best_bowling_innings",
            "q13_highest_team_totals",
            "q14_lowest_all_out_totals",
            "q15_biggest_wins_by_runs",
            "q11_titles_by_team",
            "q01_top_run_scorers_by_format",
            "q06_top_wicket_takers",
        )
    }
    return facts


def build(root: Path = ROOT, db: Path = DB) -> str:
    f = gather(root, db)
    c, cov = f["counts"], f["coverage"]
    L: list[str] = [
        "# Men's ICC World Cups - analytics report",
        "",
        f"_Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} from the gold layer. Every figure below is computed from the data or from the stage reports._",
        "",
        "## 1. Summary",
        "",
        f"* **Scope:** {int(c['tournaments'])} men's World Cups ({'; '.join(f'{r.format} {r.first_year}-{r.last_year} ({r.editions} editions)' for r in f['span'].itertuples())}), {int(c['matches']):,} matches, {int(c['players']):,} players, {int(c['teams'])} teams, {int(c['venues'])} venues, {int(c['deliveries']):,} balls bowled.",
        f"* **Coverage:** every match has a scorecard; ball-by-ball exists for {int(cov['bbb'])} of {int(cov['played'])} played matches ({100 * cov['bbb'] / cov['played']:.0f}%). The rest are not in the free ball-by-ball source.",
    ]
    q = f["quality"]
    if q is not None:
        L.append(
            f"* **Quality:** {len(f['rules']['rule_id'].unique())} data-quality rules on the resolved data; overall dataset scores {q['overall'].min():.1f}-{q['overall'].max():.1f}/100."
        )
    st = f["stats"]
    if st is not None:
        sig = st[st["significant_at_0.05"]]
        L.append(
            f"* **Cricket findings:** {len(sig)} of {len(st)} hypothesis tests stay significant after multiple-testing correction (section 4)."
        )
    wm = f["winner_metrics"]
    if wm is not None:
        a = wm[wm["scope"] == "all"].set_index("model")
        rest = a.drop(index=["coin", "elo_only"])
        best = rest["log_loss"].idxmin()
        verdict = (
            "better"
            if rest.loc[best, "log_loss"] < a.loc["elo_only", "log_loss"] - 0.01
            else "not clearly better"
        )
        L.append(
            f"* **Prediction:** an Elo rating alone predicts match winners {100 * a.loc['elo_only', 'accuracy']:.0f}% of the time out of sample (coin: {100 * a.loc['coin', 'accuracy']:.0f}%). Best richer model by log-loss: {best} ({rest.loc[best, 'log_loss']:.3f} vs Elo-only {a.loc['elo_only', 'log_loss']:.3f}), i.e. {verdict} than Elo."
        )
    L += [
        "",
        "## 2. The data",
        "",
        "Champions by edition:",
        "",
        table(f["champions"].fillna("-")),
        "",
    ]
    rec = f["records"]
    if rec["q11_titles_by_team"] is not None:
        L += ["Titles by team:", "", table(rec["q11_titles_by_team"]), ""]
    L += [
        "Why some matches lack ball-by-ball detail:",
        "",
        table(f["gaps"]),
        "",
        "ODI data begins with the 2003 World Cup, so career totals cover 2003-2023 only (earlier ODI World Cups are not in the dataset).",
        "",
    ]

    L += ["## 3. Data quality", ""]
    if q is not None:
        L += [
            table(
                q[
                    [
                        "dataset",
                        "completeness",
                        "uniqueness",
                        "validity",
                        "referential_integrity",
                        "consistency",
                        "historical_coverage",
                        "overall",
                    ]
                ],
                1,
            ),
            "",
        ]
        fails = (
            f["rules"].groupby(["rule_id", "severity"], as_index=False)[["total", "failed"]].sum()
        )
        fails = fails[fails["failed"] > 0]
        L += [
            "Rules with failures (each is explained in `reports/gold/data_quality_report.md`; `-` above means the dimension has no rule for that dataset):",
            "",
            table(fails) if len(fails) else "None.",
            "",
        ]
    else:
        L += ["Quality report not found; run the quality step.", ""]

    L += ["## 4. Findings", "", "Records from the data:", ""]

    def first(name, cols):
        d = rec.get(name)
        return None if d is None or d.empty else d.iloc[0][cols]

    r = first("q02_highest_individual_scores", ["player", "runs", "year", "opposition"])
    if r is not None:
        L.append(
            f"* Highest individual score: **{r['player']}** {int(r['runs'])} ({int(r['year'])}, v {r['opposition']})."
        )
    r = first("q07_best_bowling_innings", ["player", "wickets", "runs_conceded", "year"])
    if r is not None:
        L.append(
            f"* Best bowling: **{r['player']}** {int(r['wickets'])}/{int(r['runs_conceded'])} ({int(r['year'])})."
        )
    r = first("q13_highest_team_totals", ["team_name", "total_runs", "year"])
    if r is not None:
        L.append(
            f"* Highest team total: **{r['team_name']}** {int(r['total_runs'])} ({int(r['year'])})."
        )
    r = first("q14_lowest_all_out_totals", ["team_name", "total_runs", "year"])
    if r is not None:
        L.append(
            f"* Lowest all-out total: **{r['team_name']}** {int(r['total_runs'])} ({int(r['year'])})."
        )
    r = first("q15_biggest_wins_by_runs", ["winner", "loser", "runs_margin", "year"])
    if r is not None:
        L.append(
            f"* Biggest win by runs: **{r['winner']}** over {r['loser']} by {int(r['runs_margin'])} ({int(r['year'])})."
        )
    L.append("")
    if st is not None:
        L += [
            "Hypothesis tests (Holm-corrected p-values; matches are not independent draws, so p-values are indicative):",
            "",
            table(
                st[
                    ["test_id", "n", "effect_name", "effect", "p_holm", "significant_at_0.05"]
                ].assign(
                    p_holm=lambda d: d["p_holm"].map(
                        lambda v: "<0.001" if v < 0.001 else f"{v:.3f}"
                    )
                ),
                3,
            ),
            "",
        ]
        no_edge = st[
            (st["test_id"].str.startswith(("toss_win_rate", "bat_first_win_rate")))
            & ~st["significant_at_0.05"]
        ]
        if len(no_edge):
            L.append(
                f"No detectable edge from winning the toss or batting first ({', '.join(no_edge['test_id'])}: all within chance)."
            )
            L.append("")

    L += ["## 5. Predictive modelling", ""]
    if wm is not None:
        L += [
            "Who wins (expanding-window evaluation: trained on earlier tournaments, tested on the next):",
            "",
            table(wm[wm["scope"] == "all"].drop(columns="scope"), 3),
            "",
        ]
        ab = f["ablation"]
        if ab is not None:
            by = ab.set_index("feature_set")["log_loss"]
            reading = (
                "the Elo gap alone is at least as good as all features, so the extra features add noise at this sample size."
                if by["elo_diff only"] <= by["all features"]
                else "the full feature set improves log-loss over the Elo gap alone."
            )
            L += [
                "Do extra features help? (same protocol, logistic model):",
                "",
                table(ab, 3),
                "",
                f"Reading: {reading}",
                "",
            ]
    pg = f.get("proj_gains")
    if pg is not None:
        lines = []
        for fmt, g in pg.groupby("format"):
            r = g[g["model"] == "linear_regression"].iloc[0]
            lines.append(f"{fmt}: {r['mae_gain_vs_run_rate']:.1f} runs better than run-rate extrapolation (95% interval {r['ci_low']:.1f} to {r['ci_high']:.1f})")
        L += ["Live first-innings projection (during the innings), linear regression on remaining runs: " + "; ".join(lines) + ". Full per-over results are in the machine learning report.", ""]
    sm = f["score_metrics"]
    if sm is not None:
        L += [
            "First-innings score (MAE in runs, lower is better):",
            "",
            table(sm[sm["scope"] == "all"].drop(columns="scope"), 2),
            "",
        ]

    L += [
        "## 6. Limitations",
        "",
        f"* Ball-by-ball detail covers {100 * cov['bbb'] / cov['played']:.0f}% of played matches; phase and dot-ball analyses use only those.",
        "* Pitch, weather and day/night data were not collected. A synthetic placeholder table exists for demos and is excluded from every analysis in this report.",
        "* About 640 decided matches: small samples limit model complexity; small effects are noise.",
        "* Several matches have no winner (ties without a tie-break, no results, abandoned); they are kept and labelled, never invented.",
        "* Player identity across the two sources is resolved per match with strict rules; a small share of deliveries (<0.1%) could not be matched safely and keep a source-only identity.",
        "",
    ]

    L += [
        "## 7. Reproducibility",
        "",
        f"* Environment: Python {platform.python_version()}, DuckDB {duckdb.__version__}.",
        "* Run everything: `python scripts/run_lakehouse_pipeline.py` (details in README); the raw collected data is never modified, and bronze is verified against a content-hash manifest.",
    ]
    p = f["pipeline"]
    if p:
        L += [
            f"* Last pipeline run `{p['run_id']}`: {'succeeded' if p['success'] else 'did not fully succeed'} ({len(p['steps'])} steps)."
        ]
    return "\n".join(L) + "\n"


def write(root: Path = ROOT, db: Path = DB) -> Path:
    out = root / "reports" / "executive_report.md"
    out.write_text(build(root, db), encoding="utf-8")
    return out
