# ruff: noqa: E501
"""Figures for the written reports (PNG, matplotlib). Every figure is drawn from data or stage outputs."""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
FIG = REPORTS / "figures"
DB = ROOT / "data" / "warehouse" / "cricket_gold.duckdb"
COL = {"ODI": "#2a6fbb", "T20": "#e07b00"}
plt.rcParams.update({"figure.dpi": 120, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25})


def _q(sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


def _csv(rel: str) -> pd.DataFrame | None:
    p = REPORTS / rel
    return pd.read_csv(p) if p.exists() else None


def _save(fig, name: str) -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=130)
    plt.close(fig)
    return f"figures/{name}"


def coverage() -> str:
    d = _q("select format, year, played_matches p, played_with_ball_by_ball b from gold.mart_data_coverage order by format, year")
    lab = d["format"] + " " + d["year"].astype(str)
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar(lab, d["b"], color="#2a6fbb", label="with ball-by-ball")
    ax.bar(lab, d["p"] - d["b"], bottom=d["b"], color="#c9c9c9", label="scorecard only")
    ax.set_ylabel("played matches")
    ax.set_title("Ball-by-ball coverage by edition")
    ax.legend()
    plt.xticks(rotation=60, ha="right")
    return _save(fig, "coverage.png")


def scoring_trend() -> str:
    d = _q("select format, year, avg_first_innings_score a, sixes * 1.0 / matches s, runs_per_match r from gold.mart_tournament_summary order by 1, 2")
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    for f, g in d.groupby("format"):
        ax[0].plot(g["year"], g["a"], "o-", color=COL[f], label=f)
        ax[1].plot(g["year"], g["s"], "o-", color=COL[f], label=f)
        ax[2].plot(g["year"], g["r"], "o-", color=COL[f], label=f)
    for a, t in zip(ax, ["Average first-innings score", "Sixes per match", "Runs per match"], strict=True):
        a.set_title(t)
        a.legend()
    return _save(fig, "scoring_trend.png")


def toss_batfirst() -> str | None:
    t = _csv("statistical_tests.csv")
    if t is None:
        return None
    d = t[t["test_id"].str.startswith(("toss_win_rate", "bat_first_win_rate"))].copy()
    fig, ax = plt.subplots(figsize=(7, 3.4))
    y = np.arange(len(d))
    ax.errorbar(d["effect"], y, xerr=[d["effect"] - d["ci_low"], d["ci_high"] - d["effect"]], fmt="o", color="#2a6fbb", capsize=4)
    ax.axvline(0.5, ls="--", color="k")
    ax.set_yticks(y)
    ax.set_yticklabels(d["test_id"])
    ax.set_xlabel("win rate (95% interval)")
    ax.set_title("Toss and batting first: no edge distinguishable from 50%")
    return _save(fig, "toss_batfirst.png")


def phases() -> str:
    d = _q("select format, phase, 6.0*sum(total_runs)/count(*) filter (where is_legal_ball) rr, 100.0*avg(case when is_dot_ball then 1.0 else 0 end) dot, 100.0*avg(case when is_wicket then 1.0 else 0 end) wk from gold.fact_deliveries where not is_super_over and phase in ('powerplay','middle','death') group by 1, 2")
    order = ["powerplay", "middle", "death"]
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    for f, g in d.groupby("format"):
        g = g.set_index("phase").loc[order]
        for a, c in zip(ax, ["rr", "dot", "wk"], strict=True):
            a.plot(order, g[c], "o-", color=COL[f], label=f)
    for a, t in zip(ax, ["Run rate (per over)", "Dot balls (%)", "Wicket balls (%)"], strict=True):
        a.set_title(t)
        a.legend()
    return _save(fig, "phases.png")


def stats_forest() -> str | None:
    t = _csv("statistical_tests.csv")
    if t is None:
        return None
    d = t.dropna(subset=["ci_low"])
    d = d[d["effect_name"].str.contains("odds|rate ratio")].sort_values("effect")
    fig, ax = plt.subplots(figsize=(7, 0.45 * len(d) + 1.5))
    y = np.arange(len(d))
    ax.errorbar(d["effect"], y, xerr=[d["effect"] - d["ci_low"], d["ci_high"] - d["effect"]], fmt="o", color="#2a6fbb", capsize=3)
    ax.axvline(1, ls="--", color="k")
    ax.set_yticks(y)
    ax.set_yticklabels(d["test_id"])
    ax.set_xlabel("ratio (1 = no effect), 95% interval")
    ax.set_title("Ratio-type effects")
    return _save(fig, "stats_forest.png")


def projection() -> str | None:
    m = _csv("model_evaluation/innings_projection_metrics.csv")
    if m is None:
        return None
    m = m[m["scope"].str.startswith("over") & m["model"].isin(["baseline_run_rate", "linear_regression"])].copy()
    m["over"] = m["scope"].str.replace("over ", "").astype(int)
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    for a, f in zip(ax, ["T20", "ODI"], strict=True):
        for name, g in m[m["format"] == f].groupby("model"):
            a.plot(g["over"], g["mae"], "o-", label=name)
        a.set_title(f"{f}: projection error by over")
        a.set_xlabel("overs completed")
        a.set_ylabel("MAE (runs)")
        a.legend()
    return _save(fig, "projection_mae.png")


def clusters() -> list[str]:
    out = []
    for kind in ("batters", "bowlers"):
        p = ROOT / "data" / "features" / f"clusters_{kind}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        for lab, g in d.groupby("cluster_label"):
            ax.scatter(g["pc1"], g["pc2"], s=18, alpha=0.7, label=lab)
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.set_title(f"{kind.title()}: player-role clusters (PCA)")
        ax.legend(fontsize=7)
        out.append(_save(fig, f"clusters_{kind}.png"))
    return out


def consistency() -> str | None:
    d = _csv("model_evaluation/consistency_batting.csv")
    if d is None:
        return None
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.scatter(d["mean_runs"], d["cv"], s=d["innings"] * 2, alpha=0.5, color="#2a6fbb")
    for r in d.nlargest(6, "mean_runs").itertuples():
        ax.annotate(r.player.split()[-1], (r.mean_runs, r.cv), fontsize=7)
    ax.set_xlabel("mean runs per innings")
    ax.set_ylabel("coefficient of variation")
    ax.set_title("Batting consistency (>= 10 innings)")
    return _save(fig, "consistency.png")


def quality() -> str | None:
    d = _csv("gold/data_quality/dataset_scores.csv")
    if d is None:
        return None
    dims = ["completeness", "uniqueness", "validity", "referential_integrity", "consistency", "historical_coverage"]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    long = d.melt(id_vars="dataset", value_vars=dims, var_name="dimension", value_name="score").dropna()
    for i, (dim, g) in enumerate(long.groupby("dimension")):
        ax.scatter(g["score"], [x.replace("gold.", "") for x in g["dataset"]], label=dim, marker="os^vD*"[i % 6], s=45)
    ax.set_xlim(90, 100.5)
    ax.set_xlabel("score (0-100)")
    ax.set_title("Data-quality score by dataset and dimension (gold)")
    ax.legend(fontsize=7, loc="lower left")
    return _save(fig, "quality.png")


def regression() -> str | None:
    d = _csv("model_evaluation/batting_regression_logit_odds.csv")
    if d is None:
        return None
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    y = np.arange(len(d))
    ax.errorbar(d["estimate"], y, xerr=[d["estimate"] - d["ci_low"], d["ci_high"] - d["estimate"]], fmt="o", capsize=3, color="#2a6fbb")
    ax.axvline(1, ls="--", color="k")
    ax.set_xscale("log")
    ax.set_yticks(y)
    ax.set_yticklabels(d["term"])
    ax.set_title("Odds of scoring 30+ (95% interval; association, not cause)")
    return _save(fig, "batting_regression.png")


def build_all() -> dict[str, str | list[str] | None]:
    return {
        "coverage": coverage(), "scoring_trend": scoring_trend(), "toss_batfirst": toss_batfirst(), "phases": phases(),
        "stats_forest": stats_forest(), "projection": projection(), "clusters": clusters(), "consistency": consistency(),
        "quality": quality(), "regression": regression(),
    }
