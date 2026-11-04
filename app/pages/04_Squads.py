# ruff: noqa: E501
"""Squads: rosters, composition, comparison across teams, continuity and player lookup."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils.theme import AMBER, BLUE, FORMAT_COLORS, PINK, TEAL, cards, flag  # noqa: E402
from app.utils.ui import setup  # noqa: E402

ROLE_ORDER = ["batter", "wicketkeeper", "all-rounder", "bowler", "unknown"]


def role_group(r) -> str:
    s = str(r or "").lower()
    if "allrounder" in s or "all-rounder" in s:
        return "all-rounder"
    if "wicketkeeper" in s:
        return "wicketkeeper"
    if "bowler" in s:
        return "bowler"
    if "batter" in s or "batsman" in s:
        return "batter"
    return "unknown"


def bowl_type(style) -> str:
    s = str(style or "").lower()
    if not s or s == "none" or s == "nan":
        return "does not bowl"
    pace = any(k in s for k in ("fast", "medium"))
    spin = any(k in s for k in ("break", "spin", "orthodox", "chinaman", "googly", "slow"))
    if pace and spin:
        return "pace and spin"
    if pace:
        return "pace"
    return "spin" if spin else "other"


def hand(style) -> str:
    s = str(style or "").lower()
    if "left" in s:
        return "left-hand"
    return "right-hand" if "right" in s else "unknown"


if setup(
    "Squads",
    "🧢",
    "Every announced squad: who was picked, their roles, ages and styles, and how squads compare and change.",
    ["rosters", "roles and ages", "left vs right", "pace vs spin", "continuity"],
):
    sq = V.squads_all()
    sq["role_group"] = sq["playing_role"].map(role_group)
    sq["bowl_type"] = sq["bowling_style"].map(bowl_type)
    sq["bat_hand"] = sq["batting_style"].map(hand)
    t = (
        sq[["tournament_id", "tournament_name", "format", "year"]]
        .drop_duplicates()
        .sort_values(["format", "year"])
    )
    fmt = st.sidebar.radio("Format", Q.formats(), horizontal=True)
    sub = t[t["format"] == fmt]
    year = st.sidebar.select_slider(
        "Tournament year", options=sub["year"].tolist(), value=sub["year"].iloc[-1]
    )
    tid = sub[sub["year"] == year]["tournament_id"].iloc[0]
    day = sq[sq["tournament_id"] == tid]
    team = st.sidebar.selectbox("Team", sorted(day["team_name"].unique()))
    tabs = st.tabs(["Squad", "Composition", "Compare squads", "Continuity", "Player lookup"])

    with tabs[0]:
        s = day[day["team_name"] == team].copy()
        st.subheader(f"{flag(team)} {team} - {sub[sub['year'] == year]['tournament_name'].iloc[0]}")
        cap = s[s["is_captain"]]["full_name"].tolist()
        cards(
            [
                (
                    "Squad size",
                    str(len(s)),
                    f"{int(s['played_for_team'].sum())} played at least one match",
                ),
                (
                    "Average age",
                    f"{s['age_at_tournament'].mean():.1f}"
                    if s["age_at_tournament"].notna().any()
                    else "n/a",
                    "years at tournament start",
                ),
                ("Captain", ", ".join(cap) if cap else "n/a", ""),
                (
                    "Wicketkeepers",
                    str(
                        int((s["role_group"] == "wicketkeeper").sum() + s["is_wicketkeeper"].sum())
                    ),
                    "listed",
                ),
                (
                    "Left-handers",
                    str(int((s["bat_hand"] == "left-hand").sum())),
                    f"of {len(s)} batters",
                ),
            ]
        )
        a, b = st.columns([3, 2])
        with a:
            show = s[
                [
                    "full_name",
                    "playing_role",
                    "batting_style",
                    "bowling_style",
                    "age_at_tournament",
                    "matches_played",
                    "is_captain",
                    "is_wicketkeeper",
                    "is_overseas",
                    "is_withdrawn",
                ]
            ].rename(
                columns={
                    "full_name": "player",
                    "playing_role": "role",
                    "age_at_tournament": "age",
                    "matches_played": "matches",
                    "is_captain": "captain",
                    "is_wicketkeeper": "keeper",
                    "is_overseas": "overseas",
                    "is_withdrawn": "withdrawn",
                }
            )
            st.dataframe(
                show.sort_values(["matches"], ascending=False),
                hide_index=True,
                width="stretch",
                height=560,
            )
        with b:
            fig = px.bar(
                s.sort_values("age_at_tournament"),
                x="age_at_tournament",
                y="full_name",
                orientation="h",
                color="role_group",
                title="Age of each player",
                color_discrete_sequence=[BLUE, AMBER, TEAL, PINK, "#8FA0C0"],
            )
            fig.update_layout(height=560, yaxis=dict(title=""), xaxis_title="age")
            st.plotly_chart(fig, width="stretch")
        a, b = st.columns(2)
        with a:
            fig = px.bar(
                s.sort_values("matches_played"),
                x="matches_played",
                y="full_name",
                orientation="h",
                color="played_for_team",
                color_discrete_map={True: TEAL, False: "#51607f"},
                title="Matches played in the tournament (grey = never played)",
            )
            fig.update_layout(height=520, yaxis=dict(title=""))
            st.plotly_chart(fig, width="stretch")
        with b:
            fig = px.sunburst(s, path=["role_group", "bowl_type"], title="Roles and bowling types")
            fig.update_layout(height=520, margin=dict(l=4, r=4, t=50, b=4))
            st.plotly_chart(fig, width="stretch")
        if (s["source"].astype(str).str.contains("manual")).any():
            st.caption(
                "This squad was entered manually from a user-supplied image (source: manual)."
            )

    with tabs[1]:
        s = day[day["team_name"] == team]
        a, b, c = st.columns(3)
        with a:
            r = s["role_group"].value_counts()
            st.plotly_chart(C.donut(r.index, r.values, "Role mix", 340), width="stretch")
        with b:
            h = s["bat_hand"].value_counts()
            st.plotly_chart(
                C.donut(h.index, h.values, "Batting hand", 340, colors=[BLUE, AMBER, "#8FA0C0"]),
                width="stretch",
            )
        with c:
            bt = s["bowl_type"].value_counts()
            st.plotly_chart(
                C.donut(
                    bt.index,
                    bt.values,
                    "Bowling type",
                    340,
                    colors=[TEAL, PINK, AMBER, BLUE, "#8FA0C0"],
                ),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.histogram(
                    day,
                    x="age_at_tournament",
                    nbins=22,
                    color="format",
                    color_discrete_map=FORMAT_COLORS,
                    title="Age of every player in this tournament's squads",
                ).update_layout(height=340),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.box(
                    day,
                    x="role_group",
                    y="age_at_tournament",
                    color="role_group",
                    points="all",
                    title="Age by role (all teams)",
                    category_orders={"role_group": ROLE_ORDER},
                ).update_layout(height=340, showlegend=False),
                width="stretch",
            )
        bs = day["bowling_style"].fillna("does not bowl").value_counts().head(12).reset_index()
        bs.columns = ["bowling style", "players"]
        st.plotly_chart(
            px.bar(
                bs.sort_values("players"),
                x="players",
                y="bowling style",
                orientation="h",
                title="Most common bowling styles (all squads in the tournament)",
                color_discrete_sequence=[PINK],
            ).update_layout(height=380),
            width="stretch",
        )

    with tabs[2]:
        agg = (
            day.groupby("team_name")
            .agg(
                squad=("player_id", "size"),
                avg_age=("age_at_tournament", "mean"),
                played=("played_for_team", "mean"),
                left=("bat_hand", lambda x: (x == "left-hand").mean() * 100),
                pace=("bowl_type", lambda x: (x == "pace").mean() * 100),
                spin=("bowl_type", lambda x: (x == "spin").mean() * 100),
            )
            .reset_index()
        )
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.bar(
                    agg.sort_values("avg_age"),
                    x="avg_age",
                    y="team_name",
                    orientation="h",
                    color="avg_age",
                    color_continuous_scale="Sunsetdark",
                    title="Average squad age",
                    range_x=[agg["avg_age"].min() - 2, agg["avg_age"].max() + 1],
                ).update_layout(height=max(360, 26 * len(agg))),
                width="stretch",
            )
        with b:
            mix = day.groupby(["team_name", "role_group"]).size().reset_index(name="n")
            mix["share"] = 100 * mix["n"] / mix.groupby("team_name")["n"].transform("sum")
            st.plotly_chart(
                px.bar(
                    mix,
                    x="share",
                    y="team_name",
                    color="role_group",
                    orientation="h",
                    title="Role mix of each squad (%)",
                    category_orders={"role_group": ROLE_ORDER},
                ).update_layout(height=max(360, 26 * len(agg))),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            heat = agg.set_index("team_name")[["left", "pace", "spin"]]
            st.plotly_chart(
                C.heatmap(
                    heat.to_numpy(),
                    ["left-handers %", "pace %", "spin %"],
                    heat.index,
                    "Squad make-up (% of squad)",
                    max(360, 26 * len(agg)),
                    C.SEQUENTIAL,
                    ".0f",
                ),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.scatter(
                    agg,
                    x="avg_age",
                    y="left",
                    size="squad",
                    color="played",
                    labels={
                        "left": "left-hand batters (%)",
                        "avg_age": "average age",
                        "played": "share who played",
                    },
                    hover_name="team_name",
                    title="Age vs left-hand share (size = squad size, colour = share who played)",
                    color_continuous_scale="Tealgrn",
                ).update_layout(height=max(360, 26 * len(agg))),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            st.markdown("**Oldest players**")
            st.dataframe(
                day.nlargest(8, "age_at_tournament")[
                    ["full_name", "team_name", "age_at_tournament", "playing_role"]
                ].rename(columns={"age_at_tournament": "age"}),
                hide_index=True,
                width="stretch",
            )
        with b:
            st.markdown("**Youngest players**")
            st.dataframe(
                day.nsmallest(8, "age_at_tournament")[
                    ["full_name", "team_name", "age_at_tournament", "playing_role"]
                ].rename(columns={"age_at_tournament": "age"}),
                hide_index=True,
                width="stretch",
            )

    with tabs[3]:
        st.markdown(
            "**Continuity**: the share of a team's squad that was also in that team's squad at the previous edition of the same format (high = stable core)."
        )
        rows = []
        for (_f, tm), g in sq[sq["format"] == fmt].groupby(["format", "team_name"]):
            years = sorted(g["year"].unique())
            for prev, cur in zip(years, years[1:], strict=False):
                a_ids, b_ids = (
                    set(g[g["year"] == prev]["player_id"]),
                    set(g[g["year"] == cur]["player_id"]),
                )
                rows.append(
                    {
                        "team": tm,
                        "year": cur,
                        "continuity": 100 * len(a_ids & b_ids) / max(len(b_ids), 1),
                        "returning": len(a_ids & b_ids),
                    }
                )
        cont = pd.DataFrame(rows)
        if cont.empty:
            st.info("Not enough editions.")
        else:
            piv = cont.pivot_table(index="team", columns="year", values="continuity")
            st.plotly_chart(
                C.heatmap(
                    piv.to_numpy(),
                    piv.columns,
                    piv.index,
                    f"{fmt}: % of squad returning from the previous edition",
                    max(380, 28 * len(piv)),
                    C.HEAT,
                    ".0f",
                ),
                width="stretch",
            )
            a, b = st.columns(2)
            with a:
                st.plotly_chart(
                    px.line(
                        cont[
                            cont["team"].isin(
                                cont.groupby("team")["continuity"].mean().nlargest(8).index
                            )
                        ],
                        x="year",
                        y="continuity",
                        color="team",
                        markers=True,
                        title="Most stable squads over time",
                    ).update_layout(height=380),
                    width="stretch",
                )
            with b:
                avg = (
                    cont.groupby("team", as_index=False)["continuity"]
                    .mean()
                    .sort_values("continuity")
                )
                st.plotly_chart(
                    px.bar(
                        avg,
                        x="continuity",
                        y="team",
                        orientation="h",
                        color="continuity",
                        color_continuous_scale="Tealgrn",
                        title="Average continuity",
                    ).update_layout(height=380),
                    width="stretch",
                )

    with tabs[4]:
        text = st.text_input("Find a player in any squad", "Dhoni")
        found = Q.player_search(text) if text else pd.DataFrame()
        if found.empty:
            st.info("Type a name.")
        else:
            who = st.selectbox("Player", found["full_name"].tolist())
            pid = found.loc[found["full_name"] == who, "player_id"].iloc[0]
            hist = V.player_squad_history(pid)
            if hist.empty:
                st.info("Not in any squad.")
            else:
                cards(
                    [
                        ("Editions in a squad", str(len(hist)), ""),
                        ("Teams", ", ".join(sorted(hist["team"].unique())), ""),
                        ("First squad", f"{int(hist['year'].min())}", ""),
                        ("Last squad", f"{int(hist['year'].max())}", ""),
                    ]
                )
                fig = px.scatter(
                    hist,
                    x="year",
                    y="format",
                    size=hist["matches_played"] + 3,
                    color="team",
                    hover_data=["tournament", "role", "age", "captain"],
                    title="Squad appearances (size = matches played)",
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, width="stretch")
                st.dataframe(hist, hide_index=True, width="stretch")
