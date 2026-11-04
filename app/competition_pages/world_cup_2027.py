# ruff: noqa: E501
"""ICC Men's Cricket World Cup 2027: schedule, venues, teams, format and qualification (it has not been played yet)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils.database import run  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, TEAL, VIOLET, cards, note, section  # noqa: E402
from app.utils.ui import setup  # noqa: E402

PHASE_ORDER = ["Super Series", "Group Stage", "Super 7", "Semi-final", "Final"]
PHASE_COLORS = {
    "Super Series": VIOLET,
    "Group Stage": BLUE,
    "Super 7": AMBER,
    "Semi-final": PINK,
    "Final": TEAL,
}

if setup(
    "ICC Men's Cricket World Cup 2027",
    "🏆",
    "South Africa, Zimbabwe and Namibia, 2 October to 21 November 2027. It has not been played yet, so this is the schedule, the venues, the teams and how the rest of the field is decided.",
    ["14 teams", "57 matches", "12 venues", "3 host nations", "upcoming"],
):
    sch = run("select * from gold.schedule order by match_no")
    ven = run("select * from gold.venues order by matches desc, ground")
    teams = run('select * from gold.teams order by "group", team')
    phases = run("select * from gold.phases")
    qual = run("select * from gold.qualification")
    src = run("select * from gold.sources")
    sch["date"] = pd.to_datetime(sch["date"])
    first, last = sch["date"].min(), sch["date"].max()
    days = (first.date() - date.today()).days
    confirmed = int(teams["confirmed"].sum())

    tabs = st.tabs(
        ["Overview", "Schedule", "Venues", "Teams", "Format and qualification", "Sources"]
    )

    # ------------------------------------------------------------------ overview
    with tabs[0]:
        cards(
            [
                (
                    "Starts",
                    f"{first:%d %b %Y}",
                    f"{days} days to go" if days > 0 else "under way or finished",
                ),
                ("Final", f"{last:%d %b %Y}", "Wanderers, Johannesburg (reserve day 22 Nov)"),
                ("Teams", f"{confirmed} of 12 + 2", "10 confirmed; 4 places go to the qualifier"),
                ("Matches", str(len(sch)), "in 51 days"),
                ("Venues", str(len(ven)), "8 South Africa, 3 Zimbabwe, 1 Namibia"),
            ],
            [TEAL, PINK, BLUE, AMBER, VIOLET],
        )
        note(
            "<b>Not decided yet:</b> the four qualifier teams (the Cricket World Cup Qualifier is in February-March 2027) and therefore every match shown with "
            "'Qualifier A/B' or 'QF1-QF3'. The Super 7 and knockout fixtures are published as seeds (A1, B2, ...), not teams."
        )
        a, b = st.columns([3, 2])
        with a:
            g = phases.copy()
            g["start"] = pd.to_datetime(g["start"])
            g["finish"] = pd.to_datetime(g["end"]) + pd.Timedelta(days=1)
            fig = px.timeline(
                g,
                x_start="start",
                x_end="finish",
                y="phase",
                color="phase",
                color_discrete_map=PHASE_COLORS,
                text="matches",
                category_orders={"phase": PHASE_ORDER[::-1]},
                title="Tournament timeline (number = matches)",
            )
            fig.update_layout(height=340, showlegend=False, yaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        with b:
            c = sch.groupby("country").size().reset_index(name="matches")
            fig = px.pie(
                c, names="country", values="matches", hole=0.55, title="Matches by host nation"
            )
            fig.update_traces(textinfo="label+value")
            fig.update_layout(height=340, showlegend=False)
            st.plotly_chart(fig, width="stretch")
        d = sch.groupby(["date", "phase"]).size().reset_index(name="matches")
        fig = px.bar(
            d,
            x="date",
            y="matches",
            color="phase",
            color_discrete_map=PHASE_COLORS,
            category_orders={"phase": PHASE_ORDER},
            title="Matches per day",
        )
        fig.update_layout(height=340, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")
        a, b = st.columns(2)
        with a:
            wk = (
                sch.groupby("weekday")
                .size()
                .reindex(
                    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                )
                .reset_index(name="matches")
            )
            fig = px.bar(
                wk,
                x="weekday",
                y="matches",
                title="Matches by weekday",
                color_discrete_sequence=[BLUE],
            )
            fig.update_layout(height=320, xaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        with b:
            both = (
                sch[sch["phase"] == "Group Stage"]
                .groupby("date")
                .size()
                .reset_index(name="matches")
            )
            doubles = int((sch.groupby("date").size() > 1).sum())
            cards(
                [
                    ("Days with two matches", str(doubles), "mostly in the group stage"),
                    ("Rest days", str(51 - sch["date"].nunique()), "between 2 Oct and 21 Nov"),
                ],
                [TEAL, PINK],
            )
            st.caption(
                f"{len(both)} group-stage days. Semi-finals and the final each have a reserve day."
            )

    # ------------------------------------------------------------------ schedule
    with tabs[1]:
        c1, c2, c3 = st.columns(3)
        with c1:
            ph = st.selectbox("Phase", ["All", *PHASE_ORDER])
        with c2:
            names = sorted(set(sch["team1"].dropna()) | set(sch["team2"].dropna()), key=str)
            tm = st.selectbox("Team or seed", ["All", *names])
        with c3:
            ct = st.selectbox("Host nation", ["All", *sorted(sch["country"].unique())])
        v = sch.copy()
        if ph != "All":
            v = v[v["phase"] == ph]
        if tm != "All":
            v = v[(v["team1"] == tm) | (v["team2"] == tm)]
        if ct != "All":
            v = v[v["country"] == ct]
        view = v.assign(
            match=v["team1"]
            + v["team2"].map(lambda x: f"  v  {x}" if isinstance(x, str) and x else ""),
            date=v["date"].dt.strftime("%a %d %b"),
            group=v["group"].map(lambda x: f"Group {x}" if isinstance(x, str) else ""),
        )[
            [
                "match_no",
                "date",
                "phase",
                "group",
                "match",
                "ground",
                "city",
                "country",
                "reserve_day",
            ]
        ]
        st.dataframe(view, hide_index=True, width="stretch")
        st.caption(
            f"{len(view)} of {len(sch)} fixtures. Match numbers follow the ICC list. Start times are not published in the fixture list."
        )
        a, b = st.columns(2)
        with a:
            gr = sch[sch["phase"] == "Group Stage"]
            tl = sorted((set(gr["team1"]) | set(gr["team2"])) - {None})
            mat = pd.DataFrame(0, index=tl, columns=tl)
            for r in gr.itertuples():
                mat.loc[r.team1, r.team2] = 1
                mat.loc[r.team2, r.team1] = 1
            fig = go.Figure(
                go.Heatmap(
                    z=mat.to_numpy(),
                    x=tl,
                    y=tl,
                    colorscale=[[0, "rgba(255,255,255,.03)"], [1, TEAL]],
                    showscale=False,
                    xgap=2,
                    ygap=2,
                )
            )
            fig.update_layout(
                title="Who plays whom in the group stage", height=470, yaxis_autorange="reversed"
            )
            st.plotly_chart(fig, width="stretch")
        with b:
            pv = sch.groupby(["ground", "phase"]).size().reset_index(name="matches")
            order = ven.sort_values("matches")["ground"].tolist()
            fig = px.bar(
                pv,
                y="ground",
                x="matches",
                color="phase",
                orientation="h",
                color_discrete_map=PHASE_COLORS,
                category_orders={"ground": order, "phase": PHASE_ORDER},
                title="Matches per ground and phase",
            )
            fig.update_layout(height=470, yaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        tc = (
            pd.concat(
                [
                    sch[["team1", "country"]].rename(columns={"team1": "team"}),
                    sch[["team2", "country"]].rename(columns={"team2": "team"}),
                ]
            )
            .dropna()
            .query("team in @teams.team")
            .groupby(["team", "country"])
            .size()
            .reset_index(name="matches")
        )
        fig = px.bar(
            tc,
            x="team",
            y="matches",
            color="country",
            title="Where each team plays its fixed matches (group stage; Super 7 is decided by results)",
            color_discrete_sequence=[BLUE, AMBER, TEAL],
        )
        fig.update_layout(height=360, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")

    # ------------------------------------------------------------------ venues
    with tabs[2]:
        section(
            "Twelve grounds in three countries",
            "Capacities are as listed on Wikipedia; locations on the map are approximate.",
        )
        fig = px.scatter_geo(
            ven,
            lat="latitude",
            lon="longitude",
            size="matches",
            color="country",
            hover_name="ground",
            text="city",
            hover_data={
                "city": True,
                "capacity": ":,",
                "matches": True,
                "latitude": False,
                "longitude": False,
            },
            size_max=34,
            color_discrete_sequence=[BLUE, AMBER, TEAL],
            title="Where the matches are played (bubble = number of matches)",
        )
        fig.update_geos(
            scope="africa",
            lataxis_range=[-37, -14],
            lonaxis_range=[10, 36],
            showcountries=True,
            countrycolor="rgba(255,255,255,.25)",
            landcolor="rgba(255,255,255,.04)",
            bgcolor="rgba(0,0,0,0)",
            showland=True,
        )
        fig.update_traces(textposition="top center", textfont={"size": 11})
        fig.update_layout(height=560)
        st.plotly_chart(fig, width="stretch")
        a, b = st.columns(2)
        with a:
            fig = px.bar(
                ven.sort_values("capacity"),
                y="ground",
                x="capacity",
                color="country",
                orientation="h",
                color_discrete_sequence=[BLUE, AMBER, TEAL],
                title="Capacity",
            )
            fig.update_layout(height=430, yaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        with b:
            hist = ven[ven["wc_matches_2003_2023"] > 0]
            fig = px.scatter(
                hist,
                x="capacity",
                y="avg_first_innings",
                size="wc_matches_2003_2023",
                color="country",
                hover_name="ground",
                color_discrete_sequence=[BLUE, AMBER, TEAL],
                title="Past World Cup scoring at the same grounds (2003-2023, bubble = matches)",
            )
            fig.update_layout(height=430, yaxis_title="average first-innings score")
            st.plotly_chart(fig, width="stretch")
        show = ven.assign(
            first_match=pd.to_datetime(ven["first_match"]).dt.strftime("%d %b"),
            last_match=pd.to_datetime(ven["last_match"]).dt.strftime("%d %b"),
        )[
            [
                "ground",
                "city",
                "country",
                "capacity",
                "matches",
                "phases",
                "first_match",
                "last_match",
                "wc_matches_2003_2023",
                "avg_first_innings",
                "bat_first_win_pct",
            ]
        ]
        st.dataframe(show, hide_index=True, width="stretch")
        st.caption(
            "The last three columns use this project's World Cup data for the same ground (Mangaung Oval was Goodyear Park in 2003); grounds with no earlier World Cup match show nothing."
        )

    # ------------------------------------------------------------------ teams
    with tabs[3]:
        ga, gb = st.columns(2)
        for col, g in ((ga, "A"), (gb, "B")):
            with col:
                section(f"Group {g}")
                t = teams[teams["group"] == g][
                    ["team", "status", "super7_seed", "match_count_2027"]
                ].rename(columns={"super7_seed": "Super 7 seed", "match_count_2027": "fixtures"})
                st.dataframe(t, hide_index=True, width="stretch")
        st.caption(
            "The Super 7 seeds (A1, A2, ... AB4) are the placeholders the ICC used to publish the Super 7 fixtures; the real positions come from the group stage."
        )
        h = teams[teams["confirmed"]].copy()
        h["bubble"] = h["wc_titles"] + 1  # every team gets a visible bubble; larger = more titles
        a, b = st.columns(2)
        with a:
            fig = px.scatter(
                h,
                x="wc_matches",
                y="wc_win_pct",
                size="bubble",
                hover_data={"wc_titles": True, "bubble": False},
                color="group",
                text="team",
                color_discrete_sequence=[BLUE, AMBER],
                title="ODI World Cup record 2003-2023 (bigger bubble = more titles)",
            )
            fig.update_traces(textposition="top center", marker={"sizemin": 8})
            fig.update_layout(height=430, xaxis_title="matches played", yaxis_title="win %")
            st.plotly_chart(fig, width="stretch")
        with b:
            m = h.melt(
                id_vars="team",
                value_vars=["wc_titles", "wc_finals_lost"],
                var_name="result",
                value_name="count",
            )
            m["result"] = m["result"].map(
                {"wc_titles": "won the final", "wc_finals_lost": "lost the final"}
            )
            fig = px.bar(
                m[m["count"] > 0],
                x="team",
                y="count",
                color="result",
                color_discrete_sequence=[AMBER, PINK],
                title="Finals reached at the ODI World Cups in the data (2003-2023)",
            )
            fig.update_layout(height=430, xaxis_title=None)
            st.plotly_chart(fig, width="stretch")
        section(
            "The four places still to be decided",
            "Ireland, West Indies, Netherlands, Scotland and the United States are confirmed for the qualifier; the other places are open.",
        )
        q = qual[
            qual["stage"].str.startswith("Qualifier")
            | (qual["stage"] == "Cricket World Cup Qualifier")
        ][["stage", "teams", "status"]]
        st.dataframe(q, hide_index=True, width="stretch")

    # ------------------------------------------------------------------ format
    with tabs[4]:
        section("Format", "14 teams, 57 matches, in four phases and a final.")
        st.dataframe(
            phases.assign(
                start=pd.to_datetime(phases["start"]).dt.strftime("%d %b"),
                end=pd.to_datetime(phases["end"]).dt.strftime("%d %b"),
            )[["phase", "matches", "start", "end", "description"]],
            hide_index=True,
            width="stretch",
        )
        seeds = teams[teams["super7_seed"].notna()][["super7_seed", "team"]].sort_values(
            "super7_seed"
        )
        a, b = st.columns([2, 3])
        with a:
            section("Super 7 seeds as published")
            st.dataframe(
                seeds.rename(columns={"super7_seed": "seed", "team": "team (by ODI ranking)"}),
                hide_index=True,
                width="stretch",
            )
        with b:
            q2 = qual.copy()
            q2["start"] = pd.to_datetime(q2["date"])
            q2["finish"] = q2["start"] + pd.to_timedelta([0, 0, 0, 0, 18, 28, 4], unit="D")
            q2["finish"] = q2["finish"].where(
                q2["finish"] > q2["start"], q2["start"] + pd.Timedelta(days=4)
            )
            fig = px.timeline(
                q2,
                x_start="start",
                x_end="finish",
                y="stage",
                color="status",
                color_discrete_map={"confirmed": TEAL, "in progress": AMBER, "not started": BLUE},
                title="Qualification calendar",
            )
            fig.update_layout(height=380, yaxis_title=None, yaxis_autorange="reversed")
            st.plotly_chart(fig, width="stretch")
        section("How a team gets in")
        st.dataframe(
            qual.assign(date=pd.to_datetime(qual["date"]).dt.strftime("%d %b %Y"))[
                ["stage", "date", "status", "detail", "teams"]
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Sources disagree on the exact qualifier dates (22 Feb-23 Mar 2027 against 26 Feb-21 Mar 2027); both are inside late February to late March."
        )

    # ------------------------------------------------------------------ sources
    with tabs[5]:
        st.markdown(
            "Everything on this page is published information, checked on **"
            + str(src["checked"].iloc[0])
            + "**. Qualification is still running, so the teams will change."
        )
        for r in src.itertuples():
            st.markdown(f"- **{r.source}** ({r.kind}): {r.used_for}. [{r.url}]({r.url})")
        agree = int(sch["sources_agree"].fillna(False).sum())
        cards(
            [
                (
                    "Fixtures compared",
                    f"{agree} of {len(sch)}",
                    "ICC list and ESPNcricinfo agree on date, ground and teams (a qualifier is blank on ESPNcricinfo)",
                )
            ],
            [TEAL],
        )
        st.caption(
            "Refresh with `python scripts/run_competitions.py --wc2027` after the qualifier results are known."
        )
