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
from app.utils import viz_extra as X  # noqa: E402
from app.utils.theme import AMBER, BLUE, TEAL, cards, flag, section  # noqa: E402
from app.utils.ui import coverage_note, setup  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

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
    # Filters for the innings-based charts (Overview, Results timeline, Statistics): stage, team and date range
    stages_here = [x for x in X.STAGE_ORDER if x in set(inn["stage"])] or sorted(inn["stage"].dropna().unique())
    stage_f = st.sidebar.multiselect("Match stage", stages_here, default=stages_here)
    teams_here = sorted(set(inn["batting_team"]) | set(inn["bowling_team"]))
    team_f = st.sidebar.selectbox("Team", ["All teams", *teams_here])
    venues_here = sorted(inn["venue"].dropna().unique())
    venue_f = st.sidebar.selectbox("Venue", ["All venues", *venues_here])
    dates_here = sorted(inn["match_date"].astype(str).str[:10].unique())
    d_from = st.sidebar.selectbox("From date", dates_here, index=0)
    d_to = st.sidebar.selectbox("To date", dates_here, index=len(dates_here) - 1)
    day = inn["match_date"].astype(str).str[:10]
    keep = day.between(min(d_from, d_to), max(d_from, d_to))
    if stage_f:
        keep &= inn["stage"].isin(stage_f)
    if team_f != "All teams":
        keep &= (inn["batting_team"] == team_f) | (inn["bowling_team"] == team_f)
    if venue_f != "All venues":
        keep &= inn["venue"] == venue_f
    hidden = len(inn) - int(keep.sum())
    inn = inn[keep]
    if hidden:
        st.caption(
            f"Filters applied to the innings charts: {len(inn)} of {len(inn) + hidden} innings shown (stage, team, venue, dates)."
        )
    if inn.empty:
        st.warning("No innings match these filters: widen the stage, team, venue or date range.")
        st.stop()
    tabs = st.tabs(
        [
            "Overview",
            "Standings",
            "Results",
            "Awards",
            "Statistics",
            "Batting and bowling",
            "Batting analytics",
            "Bowling analytics",
        ]
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
        pick = (
            "All"
            if hasattr(st, "match_centre")  # the React fixtures centre has its own stage filters
            else st.selectbox("Stage", ["All"] + sorted(m["stage"].dropna().unique().tolist()))
        )
        view = m if pick == "All" else m[m["stage"] == pick]
        mt = view["margin_type"].fillna("")
        val = view["margin_value"].fillna(0).astype(int)
        unit = mt.where(val != 1, mt.str.rstrip("s"))  # "1 wicket", "1 run"
        scored = mt.isin(["runs", "wickets"])
        view = view.assign(
            result=(val.astype(str) + " " + unit).where(scored, mt.str.replace("_", " "))
        )
        shown = ["match_date", "stage", "team1", "team2", "winner", "result", "venue"]
        if hasattr(st, "match_centre"):
            # React dashboard: broadcast-style fixture graphics (click a fixture to open its match centre)
            st.fixtures({"tournament": row["tournament_name"], "fixtures": X.fixtures(tid)})
            with st.expander("Table view of the same fixtures"):
                st.dataframe(view[["match_id", *shown]], column_order=shown, hide_index=True, width="stretch")
        else:
            st.dataframe(view[["match_id", *shown]], column_order=shown, hide_index=True, width="stretch")
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

    with tabs[6]:
        bl = X.batting_leaders(tid)
        min_b = st.select_slider(
            "Minimum balls faced", options=[10, 20, 50, 100, 150, 300], value=50, key="bat_min_balls"
        )
        q = bl[bl["balls_faced"].fillna(0) >= min_b]
        if q.empty:
            st.info(f"No batter has faced {min_b} balls in this edition: lower the minimum.")
        else:
            st.caption(f"{len(q)} batters with at least {min_b} balls faced in this edition.")
            a, b = st.columns(2)
            with a:
                ms = q.assign(milestones=q["hundreds"].fillna(0) + q["fifties"].fillna(0)).nlargest(15, "milestones")
                ms = ms[ms["milestones"] > 0].sort_values("milestones")
                if ms.empty:
                    st.info("No fifties or hundreds in this edition (with this minimum).")
                else:
                    fig = go.Figure()
                    fig.add_bar(y=ms["player"], x=ms["hundreds"], orientation="h", name="Hundreds", marker_color=AMBER, hovertemplate="%{y}: %{x} hundreds<extra></extra>")
                    fig.add_bar(y=ms["player"], x=ms["fifties"], orientation="h", name="Fifties", marker_color=TEAL, hovertemplate="%{y}: %{x} fifties<extra></extra>")
                    fig.update_layout(barmode="stack", title="Centuries and half-centuries (top 15)", xaxis_title="Scores of 50+ (count)", height=440, legend=dict(orientation="h", y=-0.15))
                    st.plotly_chart(fig, width="stretch")
            with b:
                bd = q.assign(boundary_runs=q["fours"].fillna(0) * 4 + q["sixes"].fillna(0) * 6).nlargest(15, "boundary_runs").sort_values("boundary_runs")
                fig = go.Figure()
                fig.add_bar(y=bd["player"], x=bd["fours"], orientation="h", name="Fours", marker_color=BLUE, hovertemplate="%{y}: %{x} fours<extra></extra>")
                fig.add_bar(y=bd["player"], x=bd["sixes"], orientation="h", name="Sixes", marker_color=AMBER, hovertemplate="%{y}: %{x} sixes<extra></extra>")
                fig.update_layout(barmode="stack", title="Boundaries: fours and sixes (top 15 by boundary runs)", xaxis_title="Boundaries (count)", height=440, legend=dict(orientation="h", y=-0.15))
                st.plotly_chart(fig, width="stretch")
            fig = px.scatter(
                q.assign(boundaries=q["fours"].fillna(0) + q["sixes"].fillna(0)),
                x="balls_faced",
                y="runs",
                size="boundaries",
                color="team",
                hover_name="player",
                hover_data={"average": ":.1f", "strike_rate": ":.1f", "innings": True},
                size_max=30,
                title="Runs against balls faced (size = fours + sixes)",
                labels={"balls_faced": "Balls faced", "runs": "Runs"},
            )
            fig.update_layout(height=430)
            st.plotly_chart(fig, width="stretch")
        ed = X.batting_by_edition(fmt, 8)
        if ed.empty:
            st.info("No multi-edition batting data for this format.")
        else:
            a, b = st.columns(2)
            with a:
                fig = px.bar(
                    ed.assign(edition=ed["year"].astype(str)),
                    x="player",
                    y="runs",
                    color="edition",
                    barmode="group",
                    title=f"Runs by player and tournament ({fmt}): the 8 leading career run scorers",
                    labels={"runs": "Runs", "player": ""},
                )
                fig.update_layout(height=430)
                st.plotly_chart(fig, width="stretch")
            with b:
                fig = px.line(
                    ed.dropna(subset=["average"]),
                    x="year",
                    y="average",
                    color="player",
                    markers=True,
                    title=f"Batting average by edition ({fmt}, same 8 players)",
                    labels={"average": "Batting average (runs per dismissal)", "year": "Edition"},
                )
                fig.update_layout(height=430)
                st.plotly_chart(fig, width="stretch")
                st.caption("Averages from very few innings are noisy: hover to see runs and innings for each point.")

    with tabs[7]:
        wl = X.bowling_leaders(tid)
        min_w = st.select_slider(
            "Minimum balls bowled", options=[10, 20, 50, 100, 150, 300], value=50, key="bowl_min_balls"
        )
        q = wl[wl["balls_bowled"].fillna(0) >= min_w]
        if q.empty:
            st.info(f"No bowler has bowled {min_w} balls in this edition: lower the minimum.")
        else:
            st.caption(f"{len(q)} bowlers with at least {min_w} balls bowled in this edition.")
            a, b = st.columns(2)
            with a:
                aq = q.dropna(subset=["average", "strike_rate"])
                if aq.empty:
                    st.info("Bowling average needs at least one wicket: none among these bowlers.")
                else:
                    fig = px.scatter(
                        aq,
                        x="strike_rate",
                        y="average",
                        size="wickets",
                        color="team",
                        hover_name="player",
                        hover_data={"economy": ":.2f", "overs": True, "wickets": True},
                        size_max=30,
                        title="Bowling average against strike rate (size = wickets; bottom-left is best)",
                        labels={"strike_rate": "Strike rate (balls per wicket)", "average": "Bowling average (runs per wicket)"},
                    )
                    fig.update_layout(height=430)
                    st.plotly_chart(fig, width="stretch")
            with b:
                top = q.nlargest(10, "wickets").sort_values("wickets")
                fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.04, subplot_titles=("Overs bowled", "Runs conceded", "Wickets"))
                for i, (col, colour) in enumerate((("overs", BLUE), ("runs_conceded", AMBER), ("wickets", TEAL)), start=1):
                    fig.add_bar(y=top["player"], x=top[col], orientation="h", marker_color=colour, showlegend=False, hovertemplate="%{y}: %{x}<extra></extra>", row=1, col=i)
                fig.update_layout(title="Overs, runs conceded and wickets: the 10 leading wicket-takers", height=430)
                st.plotly_chart(fig, width="stretch")
        if len(q):
            a, b = st.columns(2)
            with a:
                dq = q[q["dots"].fillna(0) > 0].nlargest(12, "dots").sort_values("dots")
                if len(dq):
                    fig = px.bar(dq, x="dots", y="player", orientation="h", color="team", hover_data={"balls_bowled": True, "economy": ":.2f"}, title="Dot balls bowled (top 12)", labels={"dots": "Dot balls", "player": ""})
                    fig.update_layout(height=420, legend=dict(orientation="h", y=-0.2))
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("Dot balls come from ball-by-ball data, which this edition does not have for these bowlers.")
            with b:
                mq = q[q["maidens"].fillna(0) > 0].nlargest(12, "maidens").sort_values("maidens")
                if len(mq):
                    fig = px.bar(mq, x="maidens", y="player", orientation="h", color="team", hover_data={"overs": True, "wickets": True}, title="Maiden overs (top 12)", labels={"maidens": "Maiden overs", "player": ""})
                    fig.update_layout(height=420, legend=dict(orientation="h", y=-0.2), xaxis=dict(dtick=1))
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("No maiden overs bowled in this edition (with this minimum).")
        em = X.bowling_economy_matrix(fmt, 12)
        if len(em):
            pv = em.pivot_table(index="player", columns="year", values="economy")
            pv = pv.loc[pv.notna().sum(axis=1).sort_values(ascending=False).index]
            fig = go.Figure(
                go.Heatmap(
                    z=pv.to_numpy(),
                    x=[str(c) for c in pv.columns],
                    y=pv.index,
                    colorscale="RdYlGn_r",
                    colorbar=dict(title="Economy"),
                    hovertemplate="%{y}, %{x}: %{z:.2f} runs per over<extra></extra>",
                )
            )
            fig.update_layout(title=f"Economy rate by player and edition ({fmt}; blank = bowled under 30 balls)", height=max(360, 30 * len(pv) + 120), xaxis_title="Edition", yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, width="stretch")
        be = X.bowling_by_edition(fmt, max(min_w, 30))
        if len(be) >= 10:
            a, b = st.columns(2)
            with a:
                fig = px.box(be.assign(edition=be["year"].astype(str)), x="edition", y="economy", points="all", hover_name="player", title=f"Economy rate distribution by edition ({fmt}, bowlers with {max(min_w, 30)}+ balls)", labels={"economy": "Economy (runs per over)", "edition": "Edition"})
                fig.update_layout(height=400)
                st.plotly_chart(fig, width="stretch")
            with b:
                bw = be.dropna(subset=["strike_rate"])
                fig = px.box(bw.assign(edition=bw["year"].astype(str)), x="edition", y="strike_rate", points="all", hover_name="player", title="Strike rate distribution by edition (balls per wicket)", labels={"strike_rate": "Balls per wicket", "edition": "Edition"})
                fig.update_layout(height=400)
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("Too few qualified bowlers across editions for distribution charts: lower the minimum.")
