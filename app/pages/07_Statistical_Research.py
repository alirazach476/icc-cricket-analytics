# ruff: noqa: E501
"""Statistical research: questions, tests, intervals, effect sizes, regressions, conclusions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils.database import run  # noqa: E402
from app.utils.theme import AMBER, BLUE, FORMAT_COLORS, PINK, TEAL, cards  # noqa: E402
from app.utils.ui import setup  # noqa: E402
from src.analytics.stats_tests import wilson_ci  # noqa: E402
from src.features.match_features import FEATURES_WINNER  # noqa: E402


def conclusion(r) -> str:
    """One plain-language sentence per test, generated from the numbers (never typed)."""
    sig = bool(r["significant_at_0.05"])
    p = "<0.001" if r["p_holm"] < 0.001 else f"{r['p_holm']:.3f}"
    ci = "" if pd.isna(r["ci_low"]) else f" (95% CI {r['ci_low']:.3f} to {r['ci_high']:.3f})"
    verdict = "evidence against" if sig else "no reliable evidence against"
    return f"**{r['test_id']}**: {r['effect_name']} = {r['effect']:.3f}{ci}; Holm-adjusted p = {p}, so there is {verdict} the null hypothesis ({r['hypothesis']}). n = {int(r['n']):,}."


if setup(
    "Statistical Research",
    "🔬",
    "Research questions answered with tests, confidence intervals, effect sizes and regressions - corrected for multiple comparisons.",
    ["Holm correction", "95% intervals", "effect sizes", "regression"],
):
    tests = A.report_csv("statistical_tests.csv")
    if tests is None:
        st.info("Run `python scripts/run_statistical_tests.py`.")
    else:
        sig = tests[tests["significant_at_0.05"]]
        cards(
            [
                ("Tests run", str(len(tests)), "pre-specified"),
                ("Significant", str(len(sig)), "after Holm correction"),
                ("Not significant", str(len(tests) - len(sig)), "cannot reject the null"),
                ("Largest sample", f"{int(tests['n'].max()):,}", "observations"),
            ],
            [TEAL, AMBER, BLUE, PINK],
        )
        st.caption(
            "Matches are not independent draws (teams and tournaments repeat), so p-values are indicative. With large samples, tiny effects become significant: read the effect size."
        )
        tabs = st.tabs(
            [
                "Research questions",
                "Tests and intervals",
                "Visualisations",
                "Regression",
                "Written conclusions",
            ]
        )

        with tabs[0]:
            q = tests[["test_id", "hypothesis", "method", "n"]].rename(
                columns={"hypothesis": "null hypothesis"}
            )
            st.dataframe(q, hide_index=True, width="stretch")

        with tabs[1]:
            show = tests[
                [
                    "test_id",
                    "n",
                    "effect_name",
                    "effect",
                    "ci_low",
                    "ci_high",
                    "p_value",
                    "p_holm",
                    "significant_at_0.05",
                ]
            ].round(4)
            st.dataframe(show, hide_index=True, width="stretch")
            a, b = st.columns(2)
            with a:
                with_ci = tests.dropna(subset=["ci_low"]).copy()
                kind = st.selectbox(
                    "Forest plot by effect type", sorted(with_ci["effect_name"].unique())
                )
                d = with_ci[with_ci["effect_name"] == kind].sort_values("effect")
                ref = (
                    1.0 if ("ratio" in kind or "odds" in kind) else (0.5 if "rate" in kind else 0.0)
                )
                fig = go.Figure(
                    go.Scatter(
                        x=d["effect"],
                        y=d["test_id"],
                        mode="markers",
                        error_x=dict(
                            type="data",
                            symmetric=False,
                            array=d["ci_high"] - d["effect"],
                            arrayminus=d["effect"] - d["ci_low"],
                        ),
                        marker=dict(
                            size=10,
                            color=[TEAL if s else "#8FA0C0" for s in d["significant_at_0.05"]],
                        ),
                    )
                )
                fig.add_vline(x=ref, line_dash="dash", line_color="rgba(255,255,255,.5)")
                fig.update_layout(
                    title=f"{kind} with 95% intervals (teal = significant)",
                    height=max(300, 60 * len(d) + 140),
                )
                st.plotly_chart(fig, width="stretch")
            with b:
                vt = tests.copy()
                vt["abs_effect"] = vt["effect"]
                st.plotly_chart(
                    C.volcano(
                        vt, "effect", "p_holm", "test_id", "Effect vs significance (adjusted)", 420
                    ),
                    width="stretch",
                )
            p = tests[["test_id", "p_value", "p_holm"]].melt(
                id_vars="test_id", var_name="which", value_name="p"
            )
            fig = px.bar(
                p,
                x="test_id",
                y="p",
                color="which",
                barmode="group",
                title="Raw vs Holm-adjusted p-values",
                color_discrete_map={"p_value": BLUE, "p_holm": AMBER},
            )
            fig.add_hline(y=0.05, line_dash="dash", line_color="rgba(255,255,255,.5)")
            fig.update_layout(height=380, xaxis_tickangle=-60)
            st.plotly_chart(fig, width="stretch")

        with tabs[2]:
            fi = run(
                "select format, year, first_innings_runs from gold.fact_matches where first_innings_runs is not null and not is_dls and is_completed"
            )
            a, b = st.columns(2)
            with a:
                fig = px.scatter(
                    fi,
                    x="year",
                    y="first_innings_runs",
                    color="format",
                    trendline="ols",
                    color_discrete_map=FORMAT_COLORS,
                    opacity=0.4,
                    title="First-innings totals by year with OLS trend",
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, width="stretch")
            with b:
                res = []
                for f, g in fi.groupby("format"):
                    coef = np.polyfit(g["year"], g["first_innings_runs"], 1)
                    res.append(
                        pd.DataFrame(
                            {
                                "format": f,
                                "residual": g["first_innings_runs"] - np.polyval(coef, g["year"]),
                            }
                        )
                    )
                st.plotly_chart(
                    px.histogram(
                        pd.concat(res),
                        x="residual",
                        color="format",
                        barmode="overlay",
                        opacity=0.7,
                        nbins=30,
                        color_discrete_map=FORMAT_COLORS,
                        title="Residuals of the trend line (should be roughly bell-shaped)",
                    ).update_layout(height=400),
                    width="stretch",
                )
            a, b = st.columns(2)
            with a:
                ecdf = px.ecdf(
                    fi,
                    x="first_innings_runs",
                    color="format",
                    color_discrete_map=FORMAT_COLORS,
                    title="Distribution of first-innings totals (ECDF)",
                )
                ecdf.update_layout(height=360)
                st.plotly_chart(ecdf, width="stretch")
            with b:
                bf = run(
                    "select format, count(*) filter (where winner_id = batting_first_team_id) as wins, count(*) as n from gold.fact_matches where is_completed and not is_walkover and not is_tie and winner_id is not null group by 1"
                )
                bf["rate"] = bf["wins"] / bf["n"]
                ci = [wilson_ci(int(w), int(n)) for w, n in zip(bf["wins"], bf["n"], strict=True)]
                fig = go.Figure(
                    go.Scatter(
                        x=bf["format"],
                        y=bf["rate"],
                        mode="markers",
                        error_y=dict(
                            type="data",
                            symmetric=False,
                            array=[c[1] - r for c, r in zip(ci, bf["rate"], strict=True)],
                            arrayminus=[r - c[0] for c, r in zip(ci, bf["rate"], strict=True)],
                        ),
                        marker=dict(size=14, color=TEAL),
                    )
                )
                fig.add_hline(y=0.5, line_dash="dash", line_color="rgba(255,255,255,.5)")
                fig.update_layout(
                    title="Batting-first win rate with 95% interval",
                    yaxis_range=[0.3, 0.7],
                    height=360,
                )
                st.plotly_chart(fig, width="stretch")
            feats = A.feature_parquet("match_features.parquet")
            if feats is not None:
                lab = feats[feats["y_a_wins"].notna()].copy()
                lab["bin"] = pd.qcut(lab["elo_diff"], 10, duplicates="drop")
                g = (
                    lab.groupby("bin", observed=True)
                    .agg(elo=("elo_diff", "mean"), win=("y_a_wins", "mean"), n=("y_a_wins", "size"))
                    .reset_index(drop=True)
                )
                curve = pd.DataFrame({"elo": np.linspace(g["elo"].min(), g["elo"].max(), 60)})
                curve["expected"] = 1 / (1 + 10 ** (-curve["elo"] / 400))
                fig = px.scatter(
                    g,
                    x="elo",
                    y="win",
                    size="n",
                    title="Does the Elo gap predict the winner? (observed win rate by Elo-gap decile vs Elo's own curve)",
                    color_discrete_sequence=[AMBER],
                )
                fig.add_trace(
                    go.Scatter(
                        x=curve["elo"],
                        y=curve["expected"],
                        mode="lines",
                        name="Elo expectation",
                        line=dict(color=TEAL, width=3),
                    )
                )
                fig.update_layout(
                    height=400,
                    yaxis_tickformat=".0%",
                    xaxis_title="Elo difference (team A - team B)",
                    yaxis_title="team A win rate",
                )
                st.plotly_chart(fig, width="stretch")
                corr = feats[FEATURES_WINNER].corr()
                st.plotly_chart(
                    C.heatmap(
                        corr.to_numpy(),
                        corr.columns,
                        corr.columns,
                        "Feature correlations (team-strength features overlap heavily)",
                        520,
                        C.DIVERGING,
                        ".2f",
                        zmid=0,
                    ),
                    width="stretch",
                )
            ch = run(
                "select format, target, (winner_id = batting_second_team_id)::int as chased from gold.fact_matches where is_completed and not is_dls and not is_tie and winner_id is not null and target is not null"
            )
            parts = []
            for f, g in ch.groupby("format"):
                g = g.assign(bin=pd.qcut(g["target"], 6, duplicates="drop"))
                r = (
                    g.groupby("bin", observed=True)
                    .agg(target=("target", "mean"), rate=("chased", "mean"), n=("chased", "size"))
                    .reset_index(drop=True)
                )
                parts.append(r.assign(format=f))
            st.plotly_chart(
                px.line(
                    pd.concat(parts),
                    x="target",
                    y="rate",
                    color="format",
                    markers=True,
                    color_discrete_map=FORMAT_COLORS,
                    title="Share of chases won, by target size",
                ).update_layout(height=340, yaxis_tickformat=".0%"),
                width="stretch",
            )
            top = run(
                "select v.venue_name, f.first_innings_runs, f.format from gold.fact_matches f join gold.dim_venues v using (venue_id) where f.first_innings_runs is not null and not f.is_dls and f.format = 'T20' and v.venue_name in (select v2.venue_name from gold.fact_matches f2 join gold.dim_venues v2 using (venue_id) where f2.format = 'T20' group by 1 having count(*) >= 8)"
            )
            nv = top["venue_name"].nunique()
            st.plotly_chart(
                px.box(
                    top,
                    y="venue_name",
                    x="first_innings_runs",
                    color="venue_name",
                    title="T20 first-innings totals by ground (8+ matches): do grounds differ?",
                ).update_layout(height=max(420, 30 * nv), showlegend=False),
                width="stretch",
            )

        with tabs[3]:
            ols, logit = (
                A.report_csv("model_evaluation/batting_regression_ols.csv"),
                A.report_csv("model_evaluation/batting_regression_logit_odds.csv"),
            )
            if ols is None:
                st.info("Run `python scripts/run_player_models.py`.")
            else:
                st.markdown(
                    "**What is associated with higher individual batting scores?** (11,125 innings; standard errors clustered by player). Associations, not causes."
                )
                a, b = st.columns(2)
                with a:
                    fig = go.Figure(
                        go.Scatter(
                            x=ols["estimate"],
                            y=ols["term"],
                            mode="markers",
                            error_x=dict(
                                type="data",
                                symmetric=False,
                                array=ols["ci_high"] - ols["estimate"],
                                arrayminus=ols["estimate"] - ols["ci_low"],
                            ),
                            marker=dict(
                                size=10,
                                color=[TEAL if p < 0.05 else "#8FA0C0" for p in ols["p_value"]],
                            ),
                        )
                    )
                    fig.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,.5)")
                    fig.update_layout(
                        title="OLS on log(1 + runs): coefficients with 95% intervals", height=400
                    )
                    st.plotly_chart(fig, width="stretch")
                with b:
                    fig = go.Figure(
                        go.Scatter(
                            x=logit["estimate"],
                            y=logit["term"],
                            mode="markers",
                            error_x=dict(
                                type="data",
                                symmetric=False,
                                array=logit["ci_high"] - logit["estimate"],
                                arrayminus=logit["estimate"] - logit["ci_low"],
                            ),
                            marker=dict(
                                size=10,
                                color=[TEAL if p < 0.05 else "#8FA0C0" for p in logit["p_value"]],
                            ),
                        )
                    )
                    fig.add_vline(x=1, line_dash="dash", line_color="rgba(255,255,255,.5)")
                    fig.update_xaxes(type="log")
                    fig.update_layout(title="Odds ratios for scoring 30+", height=400)
                    st.plotly_chart(fig, width="stretch")
                st.dataframe(ols.round(3), hide_index=True, width="stretch")
                st.dataframe(logit.round(3), hide_index=True, width="stretch")
                st.caption(
                    "Not modelled: scoring phase per innings, pitch and weather (not collected). Elo advantage is the pre-match rating gap in units of 100."
                )

        with tabs[4]:
            for _, r in tests.iterrows():
                st.markdown("* " + conclusion(r))
            st.success(
                f"{len(sig)} of {len(tests)} tests remain significant after multiple-testing correction."
            )
