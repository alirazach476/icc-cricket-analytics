# ruff: noqa: E501
"""Tournament explorer: filter, standings, summary, awards, statistics."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils.theme import AMBER, BLUE, TEAL, cards, flag, section  # noqa: E402
from app.utils.ui import coverage_note, setup  # noqa: E402

if setup(
    "Tournament Explorer",
    "🏆",
    "Standings, results, awards and statistics for every edition.",
    ["format filter", "standings", "awards", "statistics"],
):
    t = Q.tournaments()
    fmt = st.sidebar.radio("Format", Q.formats(), horizontal=True)
    sub = t[t["format"] == fmt].reset_index(drop=True)
    year = st.sidebar.select_slider(
        "Tournament year", options=sub["year"].tolist(), value=sub["year"].iloc[-1]
    )
    row = sub[sub["year"] == year].iloc[0]
    tid = row["tournament_id"]
    st.subheader(row["tournament_name"])
    cards(
        [
            (
                "Champion",
                f"{flag(row['winner'] or '')} {row['winner'] or '-'}",
                f"runner-up: {row['runner_up'] or '-'}",
            ),
            ("Player of the tournament", row["player_of_tournament"] or "-", "award"),
            ("Matches", str(int(row["matches"])), f"host: {row['host_country'] or 'n/a'}"),
            ("Runs per match", f"{row['runs_per_match']:.0f}", "both innings"),
            ("Sixes", str(int(row["sixes"])), "whole tournament"),
        ]
    )
    inn = V.tournament_innings(tid)
    tabs = st.tabs(
        ["Overview", "Standings", "Results", "Awards", "Statistics", "Batting and bowling"]
    )

    with tabs[0]:
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.box(
                    inn,
                    x="stage",
                    y="total_runs",
                    color="stage",
                    points="all",
                    title="Innings totals by stage",
                    hover_data=["batting_team", "bowling_team"],
                ).update_layout(height=400, showlegend=False),
                width="stretch",
            )
        with b:
            ms = V.match_scores(tid)
            ms["result"] = ms["bat_first_won"].map(
                {True: "bat-first side won", False: "chasing side won"}
            )
            fig = px.scatter(
                ms,
                x="first_innings",
                y="second_innings",
                color="result",
                hover_data=["team1_name", "team2_name", "winner_name"],
                title="First vs second innings score (above the line = chasing side scored more)",
                color_discrete_map={"bat-first side won": BLUE, "chasing side won": AMBER},
            )
            lim = [0, max(ms["first_innings"].max(), ms["second_innings"].max()) * 1.05]
            fig.add_trace(
                go.Scatter(
                    x=lim,
                    y=lim,
                    mode="lines",
                    line=dict(dash="dash", color="rgba(255,255,255,.4)"),
                    showlegend=False,
                )
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width="stretch")
        a, b, c = st.columns(3)
        with a:
            stg = A.stage_stats(tid)
            st.plotly_chart(
                px.bar(
                    stg,
                    x="stage",
                    y="matches",
                    text="matches",
                    title="Matches by stage",
                    color_discrete_sequence=[TEAL],
                ).update_layout(height=330),
                width="stretch",
            )
        with b:
            d = inn.groupby("batting_team", as_index=False).agg(
                runs=("total_runs", "sum"), wickets=("wickets", "sum")
            )
            fig = px.treemap(
                d,
                path=["batting_team"],
                values="runs",
                color="wickets",
                color_continuous_scale="Tealgrn",
                title="Runs scored by team (colour = wickets lost)",
            )
            fig.update_layout(height=330, margin=dict(l=4, r=4, t=50, b=4))
            st.plotly_chart(fig, width="stretch")
        with c:
            dis = V.tournament_dismissals(tid)
            if len(dis):
                st.plotly_chart(
                    C.donut(
                        dis["dismissal_type"],
                        dis["wickets"],
                        "How wickets fell (ball-by-ball matches)",
                        330,
                    ),
                    width="stretch",
                )
            else:
                st.info("No ball-by-ball dismissals for this edition.")
        ve = V.tournament_venues(tid)
        st.plotly_chart(
            px.bar(
                ve.sort_values("matches"),
                x="matches",
                y="venue_name",
                orientation="h",
                color="avg_first_innings",
                color_continuous_scale="Sunsetdark",
                title="Venues (colour = average first-innings score)",
            ).update_layout(height=max(300, 34 * len(ve))),
            width="stretch",
        )

    with tabs[1]:
        s = Q.standings(tid)
        if len(s):
            groups = s["group"].unique().tolist()
            pick = st.selectbox("Group / stage", groups)
            g = s[s["group"] == pick]
            a, b = st.columns([3, 2])
            with a:
                st.dataframe(g, hide_index=True, width="stretch")
            with b:
                st.plotly_chart(
                    px.bar(
                        g.sort_values("points"),
                        x="points",
                        y="team",
                        orientation="h",
                        color="nrr",
                        color_continuous_scale="RdYlGn",
                        title="Points (colour = net run rate)",
                    ).update_layout(height=340),
                    width="stretch",
                )
            stack = g.melt(
                id_vars="team",
                value_vars=["wins", "losses", "ties", "nr"],
                var_name="result",
                value_name="matches",
            )
            st.plotly_chart(
                px.bar(
                    stack,
                    x="team",
                    y="matches",
                    color="result",
                    title="Results by team",
                    color_discrete_map={
                        "wins": TEAL,
                        "losses": "#FF5C8A",
                        "ties": AMBER,
                        "nr": "#8FA0C0",
                    },
                ).update_layout(height=340),
                width="stretch",
            )
            hm = s.pivot_table(index="team", columns="group", values="points")
            st.plotly_chart(
                C.heatmap(
                    hm.to_numpy(),
                    hm.columns,
                    hm.index,
                    "Points across all groups of the edition",
                    420,
                    C.SEQUENTIAL,
                    ".0f",
                ),
                width="stretch",
            )
        else:
            st.info("No standings for this edition.")
        st.caption(
            "Super-stage tables (Super Six / Super Eight) include results carried over from the first round, as in the source."
        )

    with tabs[2]:
        m = Q.matches_of(tid)
        pick = st.selectbox("Stage", ["All"] + sorted(m["stage"].dropna().unique().tolist()))
        view = m if pick == "All" else m[m["stage"] == pick]
        mt = view["margin_type"].fillna("")
        val = view["margin_value"].fillna(0).astype(int)
        unit = mt.where(val != 1, mt.str.rstrip("s"))  # "1 wicket", "1 run"
        scored = mt.isin(["runs", "wickets"])
        view = view.assign(
            result=(val.astype(str) + " " + unit).where(scored, mt.str.replace("_", " "))
        )
        shown = ["match_date", "stage", "team1", "team2", "winner", "result", "venue"]
        st.dataframe(
            view[["match_id", *shown]],
            column_order=shown,
            hide_index=True,
            width="stretch",
        )
        res = inn.assign(match=lambda d: d["match_id"])
        fig = px.line(
            inn.sort_values("match_date"),
            x="match_date",
            y="total_runs",
            color="innings_number",
            markers=True,
            title="Innings totals through the tournament",
            hover_data=["batting_team", "bowling_team"],
        )
        fig.update_layout(height=360)
        st.plotly_chart(fig, width="stretch")

    with tabs[3]:
        a, b = st.columns(2)
        with a:
            section("Tournament awards")
            aw = A.awards(tid)
            if len(aw):
                cards([(r.award, r.recipient, "") for r in aw.itertuples()])
            else:
                st.info("No awards recorded.")
        with b:
            section("Player of the Match awards")
            pm = A.player_of_match_leaders(tid)
            st.plotly_chart(
                px.bar(
                    pm.sort_values("awards"),
                    x="awards",
                    y="player",
                    orientation="h",
                    color_discrete_sequence=[AMBER],
                ).update_layout(height=320),
                width="stretch",
            )
        st.caption(
            "Player of the Tournament awards come from a user-supplied list (config/tournament_awards.csv)."
        )

    with tabs[4]:
        a, b = st.columns(2)
        with a:
            by_team = inn.groupby("batting_team", as_index=False).agg(
                fours=("fours", "sum"), sixes=("sixes", "sum")
            )
            long = by_team.melt(id_vars="batting_team", var_name="boundary", value_name="count")
            st.plotly_chart(
                px.bar(
                    long,
                    x="batting_team",
                    y="count",
                    color="boundary",
                    barmode="group",
                    title="Boundaries hit by team",
                    color_discrete_map={"fours": BLUE, "sixes": AMBER},
                ).update_layout(height=360),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.scatter(
                    inn,
                    x="run_rate",
                    y="wickets",
                    size="total_runs",
                    color="stage",
                    hover_data=["batting_team"],
                    title="Run rate vs wickets lost (size = runs)",
                ).update_layout(height=360),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.histogram(
                    inn,
                    x="total_runs",
                    nbins=20,
                    color="innings_number",
                    barmode="overlay",
                    opacity=0.7,
                    title="Distribution of innings totals",
                ).update_layout(height=340),
                width="stretch",
            )
        with b:
            ex = inn.groupby("batting_team", as_index=False)["extras"].sum().sort_values("extras")
            st.plotly_chart(
                px.bar(
                    ex,
                    x="extras",
                    y="batting_team",
                    orientation="h",
                    title="Extras received by each batting side",
                    color_discrete_sequence=["#9B7BFF"],
                ).update_layout(height=340),
                width="stretch",
            )

    with tabs[5]:
        bat, bowl = V.batter_bubble(tid), V.bowler_bubble(tid)
        a, b = st.columns(2)
        with a:
            fig = px.scatter(
                bat,
                x="average",
                y="strike_rate",
                size="runs",
                color="team",
                hover_name="player",
                size_max=34,
                title="Batters: average vs strike rate (size = runs)",
            )
            fig.update_layout(height=430)
            st.plotly_chart(fig, width="stretch")
        with b:
            fig = px.scatter(
                bowl,
                x="economy",
                y="wickets",
                size="matches",
                color="team",
                hover_name="player",
                size_max=30,
                title="Bowlers: economy vs wickets (size = matches)",
            )
            fig.update_layout(height=430)
            st.plotly_chart(fig, width="stretch")
        a, b = st.columns(2)
        with a:
            tb = Q.top_batters(tid)
            st.plotly_chart(
                px.bar(
                    tb.sort_values("runs"),
                    x="runs",
                    y="player",
                    orientation="h",
                    color="strike_rate",
                    color_continuous_scale="Tealgrn",
                    title="Top run scorers",
                ).update_layout(height=400),
                width="stretch",
            )
        with b:
            tw = Q.top_bowlers(tid)
            st.plotly_chart(
                px.bar(
                    tw.sort_values("wickets"),
                    x="wickets",
                    y="player",
                    orientation="h",
                    color="economy",
                    color_continuous_scale="Sunsetdark",
                    title="Top wicket takers",
                ).update_layout(height=400),
                width="stretch",
            )
    coverage_note()
