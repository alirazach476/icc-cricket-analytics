# ruff: noqa: E501
"""CricketWorldCup Analytics - home. Run: streamlit run app/dashboard.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import database  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils.theme import AMBER, BLUE, FORMAT_COLORS, section  # noqa: E402
from app.utils.ui import coverage_note, setup  # noqa: E402

_HOME = {
    "wc": (
        "CricketWorldCup Analytics",
        "Every men's ODI and T20 World Cup in one place: matches, players, squads, ball-by-ball, statistics and predictive models.",
        [
            "ODI 2003-2023",
            "T20 2007-2026",
            "ESPNcricinfo + Cricsheet",
            "ball-by-ball for 75% of matches",
        ],
    ),
    "ct": (
        "ICC Champions Trophy Analytics",
        "The Champions Trophy editions in the data: every match, player, squad and ball by ball.",
        ["ODI format", "Cricsheet ball-by-ball", "2004-2025"],
    ),
    "wtc": (
        "ICC World Test Championship Finals",
        "The three World Test Championship finals (2021, 2023, 2025): four-innings scorecards and ball-by-ball detail.",
        ["Test format", "Cricsheet ball-by-ball", "finals only"],
    ),
}
_h = _HOME[database.competition()]
if setup(_h[0], "🏏", _h[1], _h[2]):
    t = A.totals()
    q = A.data_quality_score()
    r1 = st.columns(4)
    r1[0].metric("Tournaments", f"{int(t['tournaments'])}")
    r1[1].metric("Matches", f"{int(t['matches']):,}")
    r1[2].metric("Teams", f"{int(t['teams'])}")
    r1[3].metric("Players", f"{int(t['players']):,}")
    r2 = st.columns(4)
    r2[0].metric(
        "Total runs", f"{int(t['runs']):,}", help="Regular innings only (Super Overs excluded)."
    )
    r2[1].metric(
        "Total wickets",
        f"{int(t['wickets']):,}",
        help="Wickets in regular innings, from scorecards.",
    )
    r2[2].metric(
        "Data quality score",
        "n/a" if q is None else f"{q:.1f} / 100",
        help="Mean overall score of the gold quality rules.",
    )
    r2[3].metric(
        "Ball-by-ball coverage",
        f"{t['bbb_pct']:.0f}%",
        help="Share of played matches with ball-by-ball data.",
    )

    tt = Q.tournaments()
    hosts = V.hosts()
    section(
        "The World Cup story",
        "Where the tournaments were played, who won them, and how the game changed.",
    )
    a, b = st.columns([3, 2])
    with a:
        st.plotly_chart(C.world_map(hosts["host_country"].tolist()), width="stretch")
    with b:
        champs = tt.dropna(subset=["winner"]).copy()
        fig = go.Figure()
        for f_, g in champs.groupby("format"):
            g = g.sort_values("year").reset_index(drop=True)
            pos = ["top center" if i % 2 == 0 else "bottom center" for i in range(len(g))]
            fig.add_trace(
                go.Scatter(
                    x=g["year"],
                    y=[f_] * len(g),
                    mode="markers+text",
                    text=g["winner"],
                    textposition=pos,
                    textfont=dict(size=11),
                    marker=dict(size=16, symbol="star", color=FORMAT_COLORS[f_]),
                    name=f_,
                    hovertext=g["tournament_name"] + ": " + g["winner"],
                )
            )
        fig.update_layout(
            title="Champions timeline",
            height=420,
            showlegend=False,
            xaxis=dict(dtick=2, range=[2001, 2028]),
            yaxis=dict(
                categoryorder="array",
                categoryarray=[f for f in ["T20", "Test", "ODI"] if f in set(champs["format"])],
                showgrid=False,
            ),
        )
        st.plotly_chart(fig, width="stretch")

    a, b, c = st.columns(3)
    with a:
        titles = champs.groupby(["winner", "format"]).size().reset_index(name="titles")
        fig = px.bar(
            titles,
            x="titles",
            y="winner",
            color="format",
            orientation="h",
            color_discrete_map=FORMAT_COLORS,
            title="Titles by team",
        )
        fig.update_layout(height=380, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
    with b:
        tm = V.team_match_counts()
        fig = px.treemap(
            tm,
            path=["format", "team"],
            values="matches",
            color="matches",
            color_continuous_scale="Blues",
            title="Matches played by team",
        )
        fig.update_layout(height=380, margin=dict(l=4, r=4, t=50, b=4))
        st.plotly_chart(fig, width="stretch")
    with c:
        sb = V.stage_sunburst()
        fig = px.sunburst(
            sb, path=["format", "year", "stage"], values="matches", title="Format > edition > stage"
        )
        fig.update_layout(height=380, margin=dict(l=4, r=4, t=50, b=4))
        st.plotly_chart(fig, width="stretch")

    section(
        "How the game is changing", "Pick a measure to compare the two formats across editions."
    )
    es = V.edition_stats()
    measure = st.radio(
        "Measure",
        [
            "runs_per_match",
            "avg_first_innings_score",
            "sixes_per_match",
            "fours_per_match",
            "wickets_per_match",
            "bat_first_win_pct",
        ],
        horizontal=True,
        format_func=lambda s: s.replace("_", " "),
    )
    a, b = st.columns([3, 2])
    with a:
        fig = px.line(
            es,
            x="year",
            y=measure,
            color="format",
            markers=True,
            color_discrete_map=FORMAT_COLORS,
            title=measure.replace("_", " ").title(),
        )
        fig.update_traces(line=dict(width=3), marker=dict(size=9))
        fig.update_layout(height=370)
        st.plotly_chart(fig, width="stretch")
    with b:
        corr = es[
            [
                "runs_per_match",
                "avg_first_innings_score",
                "sixes_per_match",
                "fours_per_match",
                "wickets_per_match",
                "bat_first_win_pct",
            ]
        ].corr()
        st.plotly_chart(
            C.heatmap(
                corr.to_numpy(),
                [c.replace("_per_match", "") for c in corr.columns],
                [c.replace("_per_match", "") for c in corr.columns],
                "How the scoring measures move together",
                370,
                C.DIVERGING,
                ".2f",
                zmid=0,
            ),
            width="stretch",
        )

    a, b = st.columns(2)
    with a:
        tf = V.toss_flow()
        labels = ["toss: bat", "toss: field", "toss winner won", "toss winner lost"]
        idx = {"bat": 0, "field": 1, "toss winner won": 2, "toss winner lost": 3}
        src = [idx[r.toss_decision] for r in tf.itertuples()]
        tgt = [idx[r.outcome] for r in tf.itertuples()]
        st.plotly_chart(
            C.sankey(
                labels,
                src,
                tgt,
                tf["matches"].tolist(),
                "Does winning the toss help? (decided matches)",
                360,
                [BLUE, AMBER, "#22D3B6", "#FF5C8A"],
            ),
            width="stretch",
        )
    with b:
        st.plotly_chart(
            C.calendar_heat(
                V.match_dates(), "When World Cup matches are played (matches per month)", 360
            ),
            width="stretch",
        )

    section("Hall of fame", "Career leaders across all editions in the data (ODI from 2003).")
    fmt = st.radio("Format", Q.formats(), horizontal=True)
    a, b = st.columns(2)
    with a:
        d = V.top_batters_all(fmt)
        fig = px.bar(
            d.sort_values("runs"),
            x="runs",
            y="player",
            orientation="h",
            color="strike_rate",
            color_continuous_scale="Tealgrn",
            hover_data=["average", "hundreds"],
            title=f"{fmt}: most runs (colour = strike rate)",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
    with b:
        d = V.top_bowlers_all(fmt)
        fig = px.bar(
            d.sort_values("wickets"),
            x="wickets",
            y="player",
            orientation="h",
            color="economy",
            color_continuous_scale="Sunsetdark",
            hover_data=["average", "best_figures"],
            title=f"{fmt}: most wickets (colour = economy)",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")

    section("All tournaments")
    show = tt.drop(columns=["tournament_id"]).copy()
    st.dataframe(show, hide_index=True, width="stretch")
    coverage_note()
