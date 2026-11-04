# ruff: noqa: E501
"""Match analytics: explorer, toss, batting first vs chasing, margins, ODI vs T20, venues, trends."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import match_centre as MC  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils.theme import AMBER, BLUE, FORMAT_COLORS, PINK, TEAL, cards, flag  # noqa: E402
from app.utils.ui import setup, synthetic_banner  # noqa: E402

if setup(
    "Match Analytics",
    "📋",
    "Scorecards, toss, batting first vs chasing, winning margins, venues and trends.",
    ["match explorer", "toss analysis", "margins", "ODI vs T20", "venues"],
):
    tabs = st.tabs(
        [
            "Match explorer",
            "Toss",
            "Batting first vs chasing",
            "Winning margins",
            "ODI vs T20",
            "Venues",
            "Historical trends",
        ]
    )

    with tabs[0]:
        t = Q.tournaments()
        focus = st.session_state.get("focus_match")
        names = t["tournament_name"].tolist()
        t_index = len(t) - 1
        if focus and Q.tournament_of(focus) in names:
            t_index = names.index(Q.tournament_of(focus))
        name = st.selectbox("Tournament", names, index=t_index)
        tid = t.loc[t["tournament_name"] == name, "tournament_id"].iloc[0]
        m = Q.matches_of(tid)
        m["label"] = (
            m["match_date"].astype(str)
            + "  "
            + m["team1"]
            + " v "
            + m["team2"]
            + "  ("
            + m["stage"].fillna("")
            + ")"
        )
        m_index = 0
        if focus and (m["match_id"] == focus).any():
            m_index = int(m.index[m["match_id"] == focus][0])
        rich = {
            r["label"]: {
                "t1": r["team1"],
                "t2": r["team2"],
                "date": str(r["match_date"])[:10],
                "stage": r["stage"],
                "no": r["match_number"] if r["match_number"] == r["match_number"] else None,
                "result": MC.short_result(r),
                "venue": r["venue"],
                "bbb": bool(r["has_ball_by_ball"]),
            }
            for r in MC.match_options(tid).merge(m[["match_id", "label"]], on="match_id").to_dict("records")
        }
        # `rich` (match cards with flags) is understood by the React renderer only
        extra = {"rich": rich} if hasattr(st, "match_centre") else {}
        pick = st.selectbox("Match", m["label"].tolist(), index=m_index, **extra)
        mid = m.loc[m["label"] == pick, "match_id"].iloc[0]
        h = Q.match_header(mid).iloc[0]

        centre = getattr(st, "match_centre", None) if hasattr(st, "match_centre") else None
        if centre:
            # the premium match centre (React dashboard); the classic charts and tables stay below
            pl = MC.payload(mid)
            centre(pl)
            figs = MC.charts(mid, pl) if pl and pl["has_ball_by_ball"] else {}
            if figs:
                st.markdown("### Match analysis")
                groups = [
                    ("Progression", ["Worm", "Run rate"]),
                    ("Overs and wickets", ["Over by over", "Wickets timeline"]),
                    ("Innings and chase", ["Innings comparison", "Chase"]),
                    ("Partnerships and wickets", ["Partnerships", "Fall of wickets"]),
                ]
                groups = [(g, [n for n in ns if n in figs]) for g, ns in groups]
                groups = [(g, ns) for g, ns in groups if ns]
                for tab, (_, names_) in zip(st.tabs([g for g, _ in groups]), groups, strict=True):
                    with tab:
                        cols = st.columns(len(names_))
                        for col, n in zip(cols, names_, strict=True):
                            with col:
                                st.plotly_chart(figs[n], width="stretch")
            box = st.expander("Classic charts and tables")
        else:
            box = contextlib.nullcontext()
        with box:

            st.subheader(f"{flag(h['team1'])} {h['team1']}  v  {flag(h['team2'])} {h['team2']}")
            st.caption(f"{h['match_date']} | {h['stage']} | {h['venue']}, {h['venue_city']}")
            if h["winner"]:
                margin = (
                    f" by {int(h['margin_value'])} {h['margin_type']}"
                    if h["margin_type"] in ("runs", "wickets")
                    else ""
                )
                st.success(f"**{h['winner']}** won{margin}" + (" (DLS)" if h["is_dls"] else ""))
            else:
                st.info(f"No winner recorded ({h['margin_type'] or h['result_type']}).")
            cards(
                [
                    ("Toss", f"{h['toss_decision'] or '-'}", "decision"),
                    ("Player of the match", h["player_of_match"] or "-", ""),
                    ("Ball-by-ball", "yes" if h["has_ball_by_ball"] else "no", ""),
                    ("Format", h["format"], f"year {int(h['year'])}"),
                ]
            )
            inn = Q.match_innings(mid)
            bat, bowl = Q.match_batting(mid), Q.match_bowling(mid)
            a, b = st.columns(2)
            with a:
                fig = px.bar(
                    inn,
                    x="batting",
                    y="runs",
                    color="batting",
                    text=inn.apply(lambda r: f"{int(r['runs'])}/{int(r['wickets'])}", axis=1),
                    title="Innings totals",
                )
                fig.update_layout(height=340, showlegend=False)
                st.plotly_chart(fig, width="stretch")
            with b:
                if len(bat):
                    fig = px.bar(
                        bat.sort_values("runs"),
                        x="runs",
                        y="batter",
                        orientation="h",
                        color="team",
                        hover_data=["balls", "fours", "sixes", "sr"],
                        title="Runs by batter",
                    )
                    fig.update_layout(height=340)
                    st.plotly_chart(fig, width="stretch")
            a, b = st.columns(2)
            with a:
                if len(bowl):
                    fig = px.scatter(
                        bowl,
                        x="econ",
                        y="w",
                        size="runs",
                        color="team",
                        hover_name="bowler",
                        size_max=28,
                        title="Bowling: economy vs wickets (size = runs conceded)",
                    )
                    fig.update_layout(height=340)
                    st.plotly_chart(fig, width="stretch")
            with b:
                if len(bat):
                    bb = bat.assign(boundaries=bat["fours"].fillna(0) * 4 + bat["sixes"].fillna(0) * 6)
                    fig = px.scatter(
                        bb,
                        x="balls",
                        y="runs",
                        size="boundaries",
                        color="team",
                        hover_name="batter",
                        title="Batting: balls vs runs (size = runs from boundaries)",
                    )
                    fig.update_layout(height=340)
                    st.plotly_chart(fig, width="stretch")
            st.dataframe(inn, hide_index=True, width="stretch")
            for team in bat["team"].unique():
                st.markdown(f"**{team} batting**")
                st.dataframe(
                    bat[bat["team"] == team].drop(columns="team"), hide_index=True, width="stretch"
                )
            for team in bowl["team"].unique():
                st.markdown(f"**{team} bowling**")
                st.dataframe(
                    bowl[bowl["team"] == team].drop(columns="team"), hide_index=True, width="stretch"
                )
            if not h["has_ball_by_ball"]:
                st.caption(f"No ball-by-ball for this match: {h['ball_by_ball_gap_reason']}")
            with st.expander("Match conditions (SYNTHETIC demo data)"):
                synthetic_banner()
                syn = Q.synthetic_conditions(mid)
                if len(syn):
                    st.dataframe(syn.drop(columns=["match_id"]), hide_index=True)
                else:
                    st.write("Not loaded.")

    with tabs[1]:
        ty = A.toss_by_year()
        a, b = st.columns(2)
        with a:
            fig = px.line(
                ty,
                x="year",
                y="toss_winner_win_pct",
                color="format",
                markers=True,
                color_discrete_map=FORMAT_COLORS,
                title="Share of decided matches won by the toss winner",
            )
            fig.add_hline(y=50, line_dash="dash", line_color="rgba(255,255,255,.5)")
            fig.update_layout(height=360, yaxis_range=[20, 80])
            st.plotly_chart(fig, width="stretch")
        with b:
            st.plotly_chart(
                px.line(
                    ty,
                    x="year",
                    y="chose_field_pct",
                    color="format",
                    markers=True,
                    color_discrete_map=FORMAT_COLORS,
                    title="Share of captains choosing to field",
                ).update_layout(height=360),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            tdo = A.toss_decision_outcome()
            st.plotly_chart(
                px.bar(
                    tdo,
                    x="format",
                    y="toss_winner_win_pct",
                    color="toss_decision",
                    barmode="group",
                    text="matches",
                    title="Toss winner's win % by decision (label = matches)",
                    color_discrete_sequence=[BLUE, AMBER],
                ).update_layout(height=340),
                width="stretch",
            )
        with b:
            tf = V.toss_flow()
            labels = ["toss: bat", "toss: field", "toss winner won", "toss winner lost"]
            idx = {"bat": 0, "field": 1, "toss winner won": 2, "toss winner lost": 3}
            st.plotly_chart(
                C.sankey(
                    labels,
                    [idx[r.toss_decision] for r in tf.itertuples()],
                    [idx[r.outcome] for r in tf.itertuples()],
                    tf["matches"].tolist(),
                    "From toss to result",
                    340,
                    [BLUE, AMBER, TEAL, PINK],
                ),
                width="stretch",
            )
        st.caption(
            "A statistical test (Statistical Research page) finds no detectable toss advantage in either format."
        )

    with tabs[2]:
        bf = A.bat_first_vs_chase()
        agg = bf.groupby("format")[["bat_first_wins", "chase_wins"]].sum().reset_index()
        a, b = st.columns(2)
        with a:
            long = agg.melt(id_vars="format", var_name="result", value_name="wins")
            st.plotly_chart(
                px.bar(
                    long,
                    x="format",
                    y="wins",
                    color="result",
                    barmode="group",
                    title="Wins by batting first vs chasing",
                    color_discrete_sequence=[BLUE, AMBER],
                ).update_layout(height=360),
                width="stretch",
            )
        with b:
            bf["bat_first_pct"] = (
                100 * bf["bat_first_wins"] / (bf["bat_first_wins"] + bf["chase_wins"])
            )
            fig = px.line(
                bf,
                x="year",
                y="bat_first_pct",
                color="format",
                markers=True,
                color_discrete_map=FORMAT_COLORS,
                title="% of decided matches won by the side batting first",
            )
            fig.add_hline(y=50, line_dash="dash", line_color="rgba(255,255,255,.5)")
            fig.update_layout(height=360)
            st.plotly_chart(fig, width="stretch")
        ms = V.match_scores()
        ms["result"] = ms["bat_first_won"].map(
            {True: "bat-first side won", False: "chasing side won"}
        )
        fmt = st.radio("Format", Q.formats(), horizontal=True, key="bf_fmt")
        d = ms[ms["format"] == fmt]
        fig = px.scatter(
            d,
            x="first_innings",
            y="second_innings",
            color="result",
            color_discrete_map={"bat-first side won": BLUE, "chasing side won": AMBER},
            hover_data=["team1_name", "team2_name", "year"],
            title=f"{fmt}: first vs second innings score",
        )
        lim = [0, max(d["first_innings"].max(), d["second_innings"].max()) * 1.05]
        fig.add_trace(
            go.Scatter(
                x=lim,
                y=lim,
                mode="lines",
                line=dict(dash="dash", color="rgba(255,255,255,.4)"),
                showlegend=False,
            )
        )
        fig.update_layout(height=440)
        st.plotly_chart(fig, width="stretch")
        d = d.assign(bucket=pd.qcut(d["first_innings"], 6, duplicates="drop").astype(str))
        rate = d.groupby("bucket", as_index=False).agg(
            bat_first_win=("bat_first_won", "mean"), matches=("bat_first_won", "size")
        )
        st.plotly_chart(
            px.bar(
                rate,
                x="bucket",
                y="bat_first_win",
                text="matches",
                title="Bat-first win rate by first-innings score band (label = matches)",
                color_discrete_sequence=[TEAL],
            ).update_layout(height=320, yaxis_tickformat=".0%"),
            width="stretch",
        )

    with tabs[3]:
        mg = V.margins_by_stage()
        kind = st.radio("Margin type", ["runs", "wickets"], horizontal=True)
        d = mg[mg["margin_type"] == kind]
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.histogram(
                    d,
                    x="margin_value",
                    color="format",
                    barmode="overlay",
                    opacity=0.7,
                    nbins=30,
                    color_discrete_map=FORMAT_COLORS,
                    title=f"Winning margin ({kind})",
                ).update_layout(height=360),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.violin(
                    d,
                    x="stage",
                    y="margin_value",
                    color="format",
                    box=True,
                    color_discrete_map=FORMAT_COLORS,
                    title=f"Margin by stage ({kind})",
                ).update_layout(height=360),
                width="stretch",
            )
        tight = V.match_scores()
        tight = tight.assign(
            gap=(tight["first_innings"] - tight["second_innings"]).abs()
        ).nsmallest(12, "gap")
        st.markdown("**Closest contests by score difference**")
        st.dataframe(
            tight[
                [
                    "match_date",
                    "team1_name",
                    "team2_name",
                    "first_innings",
                    "second_innings",
                    "winner_name",
                    "gap",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
        st.dataframe(d.groupby("format")["margin_value"].describe().round(1), width="stretch")

    with tabs[4]:
        fc = A.format_comparison()
        inn = V.innings_totals()
        a, b = st.columns(2)
        with a:
            cols = ["runs_per_match", "fours_per_match", "sixes_per_match", "bat_first_win_pct"]
            norm = {f: [] for f in fc["format"]}
            for c in cols:
                top = fc[c].max()
                for f, v in zip(fc["format"], fc[c], strict=True):
                    norm[f].append(100 * v / top)
            st.plotly_chart(
                C.radar(
                    ["runs/match", "fours/match", "sixes/match", "bat-first win %"],
                    norm,
                    "ODI vs T20 profile (relative to the larger of the two)",
                ),
                width="stretch",
            )
        with b:
            st.dataframe(fc, hide_index=True, width="stretch")
            st.plotly_chart(
                px.violin(
                    inn,
                    x="format",
                    y="total_runs",
                    color="format",
                    box=True,
                    color_discrete_map=FORMAT_COLORS,
                    title="Innings totals",
                ).update_layout(height=300, showlegend=False),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.histogram(
                    inn,
                    x="wickets",
                    color="format",
                    barmode="group",
                    color_discrete_map=FORMAT_COLORS,
                    title="Wickets lost per innings",
                ).update_layout(height=340),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.box(
                    inn,
                    x="stage",
                    y="total_runs",
                    color="format",
                    color_discrete_map=FORMAT_COLORS,
                    title="Innings totals by stage",
                ).update_layout(height=340),
                width="stretch",
            )

    with tabs[5]:
        vb = V.venue_bubble()
        fmt = st.radio("Format", Q.formats(), horizontal=True, key="v_fmt")
        d = vb[vb["format"] == fmt]
        fig = px.scatter(
            d,
            x="avg_first_innings",
            y="bat_first_win_pct",
            size="matches",
            color="avg_first_innings",
            color_continuous_scale="Sunsetdark",
            hover_name="venue_name",
            hover_data=["city"],
            text="venue_name",
            title=f"{fmt}: how venues play (size = matches)",
        )
        fig.update_traces(textposition="top center", textfont=dict(size=8))
        fig.add_hline(y=50, line_dash="dash", line_color="rgba(255,255,255,.4)")
        fig.update_layout(height=520)
        st.plotly_chart(fig, width="stretch")
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.bar(
                    d.sort_values("avg_first_innings"),
                    x="avg_first_innings",
                    y="venue_name",
                    orientation="h",
                    color="matches",
                    color_continuous_scale="Tealgrn",
                    title="Average first-innings score",
                ).update_layout(height=max(380, 24 * len(d))),
                width="stretch",
            )
        with b:
            heat = d.set_index("venue_name")[["avg_first_innings", "bat_first_win_pct", "matches"]]
            z = (heat - heat.mean()) / heat.std().replace(0, 1)
            st.plotly_chart(
                C.heatmap(
                    z.to_numpy(),
                    ["avg first-innings", "bat-first win %", "matches"],
                    heat.index,
                    "Venue profile (z-scores)",
                    max(380, 24 * len(d)),
                    C.DIVERGING,
                    ".1f",
                    zmid=0,
                ),
                width="stretch",
            )

    with tabs[6]:
        tr = V.edition_stats()
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.line(
                    tr,
                    x="year",
                    y="avg_first_innings_score",
                    color="format",
                    markers=True,
                    color_discrete_map=FORMAT_COLORS,
                    title="Average first-innings score",
                ).update_layout(height=340),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.line(
                    tr,
                    x="year",
                    y="sixes_per_match",
                    color="format",
                    markers=True,
                    color_discrete_map=FORMAT_COLORS,
                    title="Sixes per match",
                ).update_layout(height=340),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.bar(
                    tr,
                    x="tournament_name",
                    y="runs_per_match",
                    color="format",
                    color_discrete_map=FORMAT_COLORS,
                    title="Runs per match by edition",
                ).update_layout(height=360, xaxis_tickangle=-60),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.scatter(
                    tr,
                    x="fours_per_match",
                    y="sixes_per_match",
                    size="matches",
                    color="format",
                    text="year",
                    color_discrete_map=FORMAT_COLORS,
                    title="Boundary mix by edition (size = matches)",
                ).update_layout(height=360),
                width="stretch",
            )
        st.plotly_chart(
            px.bar(
                tr,
                x="tournament_name",
                y=["ties", "dls_matches"],
                barmode="group",
                title="Ties and DLS-affected matches by edition",
            ).update_layout(height=320, xaxis_tickangle=-60),
            width="stretch",
        )
