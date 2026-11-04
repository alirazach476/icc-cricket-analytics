# ruff: noqa: E501
"""Statistical analysis for the Champions Trophy and the World Test Championship, computed live from their gold data."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import database  # noqa: E402
from app.utils.database import run  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, TEAL, cards  # noqa: E402
from app.utils.ui import setup  # noqa: E402
from scipy import stats  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(c - h), float(c + h)


def verdict(p: float, what: str) -> str:
    if p < 0.05:
        return f"**Evidence that {what} matters** (p = {p:.3f}): the difference is unlikely to be chance."
    return f"**No clear evidence that {what} matters** (p = {p:.3f}): the record is consistent with a coin flip."


if setup(
    "Statistics",
    "🔬",
    "Tests and confidence intervals on the matches in this competition. Small samples mean wide intervals, so read the p-values with care.",
    ["toss", "batting first", "trends", "team strength", "phases"],
):
    m = run("select * from gold.fact_matches")
    decided = m[m["winner_id"].notna()].copy()
    is_test = "Test" in set(m["format"])
    n_dec = len(decided)
    cards(
        [
            ("Matches", str(len(m)), "in the data"),
            (
                "With a winner",
                str(n_dec),
                f"{len(m) - n_dec} without (abandoned, no result"
                + (", draws)" if is_test else ")"),
            ),
            ("Editions", str(m["tournament_id"].nunique()), "tournaments"),
            ("Teams", str(len(set(m["team1_id"]) | set(m["team2_id"]))), "taking part"),
        ],
        [TEAL, BLUE, AMBER, PINK],
    )
    tabs = st.tabs(
        ["Toss", "Batting first vs chasing", "Scoring trends", "Team strength", "Phases"]
    )

    with tabs[0]:
        t = decided[decided["toss_winner_id"].notna()]
        k, n = int((t["winner_id"] == t["toss_winner_id"]).sum()), len(t)
        lo, hi = wilson(k, n)
        p = stats.binomtest(k, n, 0.5).pvalue if n else 1.0
        cards(
            [
                (
                    "Toss winner won",
                    f"{k} of {n}",
                    f"{100 * k / max(n, 1):.1f}% (95% interval {100 * lo:.0f}-{100 * hi:.0f}%)",
                )
            ],
            [TEAL],
        )
        st.markdown(verdict(p, "winning the toss"))
        by = (
            t.groupby("toss_decision")
            .apply(
                lambda g: pd.Series(
                    {
                        "matches": len(g),
                        "toss_winner_won": int((g["winner_id"] == g["toss_winner_id"]).sum()),
                    }
                ),
                include_groups=False,
            )
            .reset_index()
        )
        by["win_pct"] = 100 * by["toss_winner_won"] / by["matches"]
        by["lo"] = [
            100 * wilson(int(r.toss_winner_won), int(r.matches))[0] for r in by.itertuples()
        ]
        by["hi"] = [
            100 * wilson(int(r.toss_winner_won), int(r.matches))[1] for r in by.itertuples()
        ]
        fig = go.Figure(
            go.Bar(
                x=by["toss_decision"],
                y=by["win_pct"],
                marker_color=[BLUE, AMBER][: len(by)],
                error_y=dict(
                    type="data",
                    symmetric=False,
                    array=by["hi"] - by["win_pct"],
                    arrayminus=by["win_pct"] - by["lo"],
                ),
                text=by["matches"].map(lambda v: f"n={v}"),
            )
        )
        fig.add_hline(y=50, line_dash="dash")
        fig.update_layout(
            title="Toss winner's win rate by decision (95% interval)",
            yaxis_title="win %",
            height=380,
        )
        st.plotly_chart(fig, width="stretch")
        st.dataframe(by.round(1), hide_index=True, width="stretch")

    with tabs[1]:
        d = decided[decided["batting_first_team_id"].notna()]
        k, n = int((d["winner_id"] == d["batting_first_team_id"]).sum()), len(d)
        lo, hi = wilson(k, n)
        p = stats.binomtest(k, n, 0.5).pvalue if n else 1.0
        cards(
            [
                (
                    "Batting first won",
                    f"{k} of {n}",
                    f"{100 * k / max(n, 1):.1f}% (95% interval {100 * lo:.0f}-{100 * hi:.0f}%)",
                )
            ],
            [AMBER],
        )
        st.markdown(verdict(p, "batting first"))
        e = (
            d.groupby(["year", "tournament_name"])
            .apply(
                lambda g: pd.Series(
                    {
                        "matches": len(g),
                        "bat_first_win_pct": 100
                        * (g["winner_id"] == g["batting_first_team_id"]).mean(),
                    }
                ),
                include_groups=False,
            )
            .reset_index()
        )
        fig = px.bar(
            e,
            x="tournament_name",
            y="bat_first_win_pct",
            text="matches",
            title="Share of matches won by the side that batted first, by edition",
        )
        fig.add_hline(y=50, line_dash="dash")
        fig.update_layout(height=380, xaxis_title=None, yaxis_title="%")
        st.plotly_chart(fig, width="stretch")
        if is_test:
            share = (
                m.groupby("tournament_name")
                .apply(
                    lambda g: pd.Series(
                        {"draw_or_no_result_pct": 100 * g["winner_id"].isna().mean()}
                    ),
                    include_groups=False,
                )
                .reset_index()
            )
            st.dataframe(share.round(1), hide_index=True, width="stretch")

    with tabs[2]:
        e = (
            m.groupby(["year", "tournament_name"])
            .agg(
                matches=("match_id", "count"),
                runs_per_match=("match_runs", "mean"),
                sixes_per_match=("match_sixes", "mean"),
                wickets_per_match=("match_wickets", "mean"),
            )
            .reset_index()
        )
        a, b = st.columns(2)
        with a:
            fig = px.line(
                e, x="year", y="runs_per_match", markers=True, title="Runs per match by edition"
            )
            fig.update_layout(height=360)
            st.plotly_chart(fig, width="stretch")
        with b:
            fig = px.bar(e, x="year", y="sixes_per_match", title="Sixes per match by edition")
            fig.update_layout(height=360)
            st.plotly_chart(fig, width="stretch")
        if len(e) >= 4:
            r = stats.linregress(e["year"], e["runs_per_match"])
            st.markdown(
                f"Trend in runs per match: **{r.slope:+.1f} runs per match per year** (p = {r.pvalue:.3f}, r² = {r.rvalue**2:.2f}, {len(e)} editions)."
            )
        else:
            st.caption("Too few editions for a trend test.")
        st.dataframe(e.round(1), hide_index=True, width="stretch")

    with tabs[3]:
        rows = []
        for r in decided.itertuples():
            rows.append((r.team1_name, r.winner_id == r.team1_id))
            rows.append((r.team2_name, r.winner_id == r.team2_id))
        g = (
            pd.DataFrame(rows, columns=["team", "won"])
            .groupby("team")["won"]
            .agg(["sum", "count"])
            .reset_index()
        )
        g = g[g["count"] >= (3 if is_test else 5)]
        g["win_pct"] = 100 * g["sum"] / g["count"]
        g["lo"] = [
            100 * wilson(int(s), int(c))[0] for s, c in zip(g["sum"], g["count"], strict=True)
        ]
        g["hi"] = [
            100 * wilson(int(s), int(c))[1] for s, c in zip(g["sum"], g["count"], strict=True)
        ]
        g = g.sort_values("win_pct")
        fig = go.Figure(
            go.Bar(
                x=g["win_pct"],
                y=g["team"],
                orientation="h",
                marker_color=BLUE,
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=g["hi"] - g["win_pct"],
                    arrayminus=g["win_pct"] - g["lo"],
                ),
                text=g["count"].map(lambda v: f"n={v}"),
            )
        )
        fig.add_vline(x=50, line_dash="dash")
        fig.update_layout(
            title="Win rate with 95% Wilson interval (decided matches)",
            height=max(360, 26 * len(g)),
            xaxis_title="win %",
        )
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "Intervals that cross the dashed 50% line mean the team's record is not clearly different from average."
        )

    with tabs[4]:
        ph = run(
            "select format, year, phase, sum(total_runs) runs, count(*) filter (where is_legal_ball) balls, count(*) filter (where is_wicket) wickets from gold.fact_deliveries where not is_super_over group by all"
        )
        ph["run_rate"] = 6 * ph["runs"] / ph["balls"]
        ph["balls_per_wicket"] = ph["balls"] / ph["wickets"].replace(0, np.nan)
        order = ["powerplay", "middle", "death"]
        names = (
            {
                "powerplay": "new ball (overs 1-15)",
                "middle": "middle (16-80)",
                "death": "old ball (81+)",
            }
            if is_test
            else {"powerplay": "powerplay", "middle": "middle", "death": "death"}
        )
        ph["phase_label"] = ph["phase"].map(names)
        a, b = st.columns(2)
        with a:
            fig = px.line(
                ph.sort_values("year"),
                x="year",
                y="run_rate",
                color="phase_label",
                markers=True,
                category_orders={"phase_label": [names[o] for o in order]},
                title="Run rate by phase",
            )
            fig.update_layout(height=380)
            st.plotly_chart(fig, width="stretch")
        with b:
            fig = px.bar(
                ph.sort_values("year"),
                x="year",
                y="balls_per_wicket",
                color="phase_label",
                barmode="group",
                category_orders={"phase_label": [names[o] for o in order]},
                title="Balls per wicket by phase (higher = harder to dismiss)",
            )
            fig.update_layout(height=380)
            st.plotly_chart(fig, width="stretch")
        if database.competition() == "wtc":
            st.caption(
                "Test phases are overs 1-15 (new ball), 16-80 and 81+ (old ball / second new ball)."
            )
