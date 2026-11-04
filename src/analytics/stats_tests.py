# ruff: noqa: E501
"""Stage 10: statistical hypothesis tests on the gold layer.

Every test states its hypothesis, the data it uses (and why rows are excluded), an effect size with a
confidence interval and the p-value. p-values are then corrected for multiple testing across the whole
family (Holm), because running ~12 tests and reading raw p-values would overstate what is "significant".

Caveats, written into the report:
* Matches are not independent draws (teams and tournaments repeat), so p-values are indicative.
* "Significant" means detectable given the sample size; read the effect size and interval.
* Only matches with a decided result (winner recorded, no tie/walkover) enter win-rate tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ALPHA = 0.05
DB = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "cricket_gold.duckdb"


@dataclass
class TestResult:
    test_id: str
    hypothesis: str
    method: str
    n: int
    effect_name: str
    effect: float
    ci_low: float | None
    ci_high: float | None
    p_value: float
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    p_adjusted: float = float("nan")

    @property
    def significant(self) -> bool:
        return bool(self.p_adjusted < ALPHA)


# --------------------------------------------------------------------------- helpers
def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion (well behaved for small n)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (centre - half, centre + half)


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values (controls family-wise error)."""
    m = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p_values[idx])
        adjusted[idx] = min(1.0, running)
    return adjusted.tolist()


def cramers_v(table: np.ndarray) -> float:
    chi2 = stats.chi2_contingency(table, correction=False)[0]
    n = table.sum()
    return float(np.sqrt(chi2 / (n * (min(table.shape) - 1))))


def proportion_test(successes: int, n: int, p0: float = 0.5) -> tuple[float, float, float, float]:
    """Exact two-sided binomial test. Returns (rate, p_value, ci_low, ci_high)."""
    p = stats.binomtest(successes, n, p0).pvalue
    low, high = wilson_ci(successes, n)
    return successes / n, float(p), low, high


# --------------------------------------------------------------------------- data
def load(db: Path = DB) -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        matches = con.execute("select * from gold.fact_matches").fetchdf()
        venues = con.execute("select venue_id, venue_name from gold.dim_venues").fetchdf()
        teams = con.execute("select team_id, team_name from gold.dim_teams").fetchdf()
        tourn = con.execute(
            "select tournament_id, host_country from gold.dim_tournaments"
        ).fetchdf()
        phases = con.execute(
            "select format, phase, count(*) as balls, "
            "count(*) filter (where is_dot_ball) as dots, "
            "count(*) filter (where is_boundary) as boundaries "
            "from gold.fact_deliveries where not is_super_over "
            "and phase in ('powerplay','middle','death') group by 1, 2"
        ).fetchdf()
    finally:
        con.close()
    return {
        "matches": matches,
        "venues": venues,
        "teams": teams,
        "tournaments": tourn,
        "phases": phases,
    }


def decided(matches: pd.DataFrame) -> pd.DataFrame:
    """Completed matches with a recorded winner, no tie/walkover and known innings order."""
    m = matches[
        matches["is_completed"]
        & ~matches["is_walkover"]
        & ~matches["is_tie"]
        & matches["winner_id"].notna()
        & matches["batting_first_team_id"].notna()
    ].copy()
    m["bat_first_won"] = m["winner_id"] == m["batting_first_team_id"]
    m["toss_won_match"] = m["winner_id"] == m["toss_winner_id"]
    return m


# --------------------------------------------------------------------------- tests
def test_toss_value(d: pd.DataFrame) -> list[TestResult]:
    out = []
    for fmt, g in d[d["toss_winner_id"].notna()].groupby("format"):
        rate, p, lo, hi = proportion_test(int(g["toss_won_match"].sum()), len(g))
        out.append(
            TestResult(
                f"toss_win_rate_{fmt}",
                f"{fmt}: the toss winner wins the match 50% of the time",
                "exact binomial test vs 0.5",
                len(g),
                "toss winner win rate",
                rate,
                lo,
                hi,
                p,
                "Toss is random, so a rate away from 50% would mean the toss carries real value.",
            )
        )
    return out


def test_bat_first(d: pd.DataFrame) -> list[TestResult]:
    out = []
    for fmt, g in d.groupby("format"):
        rate, p, lo, hi = proportion_test(int(g["bat_first_won"].sum()), len(g))
        out.append(
            TestResult(
                f"bat_first_win_rate_{fmt}",
                f"{fmt}: teams batting first win 50% of matches",
                "exact binomial test vs 0.5",
                len(g),
                "bat-first win rate",
                rate,
                lo,
                hi,
                p,
                "Includes DLS-affected matches; see the sensitivity test for the target size.",
            )
        )
    return out


def test_bat_first_trend(d: pd.DataFrame) -> list[TestResult]:
    out = []
    for fmt, g in d.groupby("format"):
        x = sm.add_constant((g["year"] - g["year"].min()).astype(float))
        fit = sm.Logit(g["bat_first_won"].astype(float), x).fit(disp=0)
        coef = float(fit.params.iloc[1])
        lo, hi = (float(v) for v in fit.conf_int().iloc[1])
        out.append(
            TestResult(
                f"bat_first_trend_{fmt}",
                f"{fmt}: the bat-first win probability does not change with year",
                "logistic regression, Wald test on the year slope",
                len(g),
                "odds ratio per year",
                float(np.exp(coef)),
                float(np.exp(lo)),
                float(np.exp(hi)),
                float(fit.pvalues.iloc[1]),
                "Odds ratio below 1 means batting first has become less successful over time.",
            )
        )
    return out


def test_toss_decision(d: pd.DataFrame) -> list[TestResult]:
    out = []
    for fmt, g in d[d["toss_decision"].isin(["bat", "field"])].groupby("format"):
        table = pd.crosstab(g["toss_decision"], g["toss_won_match"]).reindex(
            index=["bat", "field"], columns=[False, True], fill_value=0
        )
        p = (
            stats.chi2_contingency(table.to_numpy())[1]
            if (table.to_numpy() > 0).all()
            else stats.fisher_exact(table.to_numpy())[1]
        )
        rates = table[True] / table.sum(axis=1)
        out.append(
            TestResult(
                f"toss_decision_{fmt}",
                f"{fmt}: toss winners win equally often whether they bat or field",
                "chi-square test of independence (Fisher exact if a cell is empty)",
                int(table.to_numpy().sum()),
                "Cramer's V",
                cramers_v(table.to_numpy() + 0.0),
                None,
                None,
                float(p),
                f"win rate when choosing bat {rates['bat']:.1%} (n={int(table.loc['bat'].sum())}), "
                f"field {rates['field']:.1%} (n={int(table.loc['field'].sum())})",
            )
        )
    return out


def test_scoring_inflation(d: pd.DataFrame) -> list[TestResult]:
    out = []
    g_all = d[d["first_innings_runs"].notna() & ~d["is_dls"]]
    for fmt, g in g_all.groupby("format"):
        x = sm.add_constant((g["year"] - g["year"].min()).astype(float))
        fit = sm.OLS(g["first_innings_runs"].astype(float), x).fit()
        lo, hi = (float(v) for v in fit.conf_int().iloc[1])
        rho = stats.spearmanr(g["year"], g["first_innings_runs"])
        out.append(
            TestResult(
                f"scoring_trend_{fmt}",
                f"{fmt}: first-innings totals do not change with year",
                "OLS regression slope (runs per year); Spearman rho as a robustness check",
                len(g),
                "runs per year",
                float(fit.params.iloc[1]),
                lo,
                hi,
                float(fit.pvalues.iloc[1]),
                f"R2={fit.rsquared:.3f}; Spearman rho={rho.statistic:.2f} (p={rho.pvalue:.3g}); "
                "DLS-affected matches excluded because their first innings can be shortened.",
            )
        )
    return out


def test_chase_vs_target(d: pd.DataFrame) -> list[TestResult]:
    out = []
    g_all = d[d["target"].notna() & ~d["is_dls"]]
    for fmt, g in g_all.groupby("format"):
        chased = (g["winner_id"] == g["batting_second_team_id"]).astype(float)
        x = sm.add_constant((g["target"] - g["target"].mean()).astype(float) / 10.0)
        fit = sm.Logit(chased, x).fit(disp=0)
        lo, hi = (float(v) for v in fit.conf_int().iloc[1])
        out.append(
            TestResult(
                f"chase_vs_target_{fmt}",
                f"{fmt}: the chasing side's win probability does not depend on the target",
                "logistic regression, Wald test (target in units of 10 runs)",
                len(g),
                "odds ratio per +10 runs of target",
                float(np.exp(fit.params.iloc[1])),
                float(np.exp(lo)),
                float(np.exp(hi)),
                float(fit.pvalues.iloc[1]),
                "A strongly negative slope is the expected sanity check: bigger targets are harder.",
            )
        )
    return out


def test_venue_effect(
    d: pd.DataFrame, venues: pd.DataFrame, min_matches: int = 6
) -> list[TestResult]:
    out = []
    g_all = d[d["first_innings_runs"].notna() & ~d["is_dls"]]
    for fmt, g in g_all.groupby("format"):
        counts = g["venue_id"].value_counts()
        keep = counts[counts >= min_matches].index
        sub = g[g["venue_id"].isin(keep)]
        groups = [v["first_innings_runs"].to_numpy() for _, v in sub.groupby("venue_id")]
        if len(groups) < 3:
            continue
        h, p = stats.kruskal(*groups)
        n = len(sub)
        out.append(
            TestResult(
                f"venue_effect_{fmt}",
                f"{fmt}: first-innings totals have the same distribution at every ground",
                f"Kruskal-Wallis across {len(groups)} grounds with >= {min_matches} matches",
                n,
                "epsilon-squared",
                float(h / (n - 1)),
                None,
                None,
                float(p),
                "Not adjusted for year or team strength, so part of the effect is era, not ground.",
            )
        )
    return out


def test_host_advantage(
    d: pd.DataFrame, tournaments: pd.DataFrame, teams: pd.DataFrame
) -> list[TestResult]:
    host = d.merge(tournaments, on="tournament_id", how="left")
    names = teams.set_index("team_id")["team_name"]
    rows = []
    for r in host.itertuples():
        hc = (r.host_country or "").lower()
        a, b = names.get(r.team1_id, ""), names.get(r.team2_id, "")
        a_host, b_host = a.lower() in hc and a != "", b.lower() in hc and b != ""
        if a_host != b_host:  # exactly one side is a host
            host_id = r.team1_id if a_host else r.team2_id
            rows.append((r.format, r.winner_id == host_id))
    df = pd.DataFrame(rows, columns=["format", "host_won"])
    out = []
    for fmt, g in df.groupby("format"):
        if len(g) < 10:
            continue
        rate, p, lo, hi = proportion_test(int(g["host_won"].sum()), len(g))
        out.append(
            TestResult(
                f"host_advantage_{fmt}",
                f"{fmt}: host nations win 50% of their decided matches against non-hosts",
                "exact binomial test vs 0.5",
                len(g),
                "host win rate",
                rate,
                lo,
                hi,
                p,
                "Hosts are matched by country name in the tournament's host_country; "
                "confounded by team strength (hosts are often strong).",
            )
        )
    return out


def test_dot_balls_by_phase(phases: pd.DataFrame) -> list[TestResult]:
    out = []
    for fmt, g in phases.groupby("format"):
        table = np.column_stack([g["dots"], g["balls"] - g["dots"]])
        chi2, p, _, _ = stats.chi2_contingency(table)
        rates = (g.set_index("phase")["dots"] / g.set_index("phase")["balls"]).round(3).to_dict()
        out.append(
            TestResult(
                f"dot_ball_phase_{fmt}",
                f"{fmt}: the share of dot balls is the same in every phase",
                "chi-square test of independence (phase x dot/non-dot)",
                int(g["balls"].sum()),
                "Cramer's V",
                cramers_v(table + 0.0),
                None,
                None,
                float(p),
                f"dot-ball share by phase: {rates}. Huge n makes tiny gaps significant; see V.",
            )
        )
    return out


def test_sixes_trend(matches: pd.DataFrame) -> list[TestResult]:
    out = []
    m = matches[matches["is_completed"] & matches["match_sixes"].notna() & ~matches["is_walkover"]]
    for fmt, g in m.groupby("format"):
        x = sm.add_constant((g["year"] - g["year"].min()).astype(float))
        fit = sm.GLM(g["match_sixes"].astype(float), x, family=sm.families.Poisson()).fit()
        lo, hi = (float(v) for v in fit.conf_int().iloc[1])
        out.append(
            TestResult(
                f"sixes_trend_{fmt}",
                f"{fmt}: sixes per match do not change with year",
                "Poisson regression, Wald test on the year slope",
                len(g),
                "rate ratio per year",
                float(np.exp(fit.params.iloc[1])),
                float(np.exp(lo)),
                float(np.exp(hi)),
                float(fit.pvalues.iloc[1]),
                "Counts are per match (both innings); matches vary in length, so this is indicative.",
            )
        )
    return out


def run_all(data: dict[str, pd.DataFrame] | None = None) -> list[TestResult]:
    data = data or load()
    d = decided(data["matches"])
    results: list[TestResult] = []
    results += test_toss_value(d)
    results += test_bat_first(d)
    results += test_bat_first_trend(d)
    results += test_toss_decision(d)
    results += test_scoring_inflation(d)
    results += test_chase_vs_target(d)
    results += test_venue_effect(d, data["venues"])
    results += test_host_advantage(d, data["tournaments"], data["teams"])
    results += test_dot_balls_by_phase(data["phases"])
    results += test_sixes_trend(data["matches"])
    adjusted = holm_adjust([r.p_value for r in results])
    for r, a in zip(results, adjusted, strict=True):
        r.p_adjusted = a
    return results


def to_frame(results: list[TestResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "test_id": r.test_id,
                "hypothesis": r.hypothesis,
                "method": r.method,
                "n": r.n,
                "effect_name": r.effect_name,
                "effect": r.effect,
                "ci_low": r.ci_low,
                "ci_high": r.ci_high,
                "p_value": r.p_value,
                "p_holm": r.p_adjusted,
                f"significant_at_{ALPHA}": r.significant,
                "note": r.note,
            }
            for r in results
        ]
    )
