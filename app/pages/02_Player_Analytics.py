# ruff: noqa: E501
"""Player analytics: search, profile, comparison, consistency, clustering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils.theme import AMBER, BLUE, FORMAT_COLORS, PINK, TEAL, cards  # noqa: E402
from app.utils.ui import coverage_note, setup  # noqa: E402


def pick_player(label: str, default: str, key: str):
    text = st.sidebar.text_input(f"Search {label}", default, key=f"s_{key}")
    found = Q.player_search(text) if text else Q.player_search("a", 20)
    if found.empty:
        st.sidebar.warning("No match.")
        return None, None
    who = st.sidebar.selectbox(label, found["full_name"].tolist(), key=f"p_{key}")
    return who, found.loc[found["full_name"] == who, "player_id"].iloc[0]


MIN_BALLS_OPTIONS = [10, 20, 50, 100, 150, 300]


def radar_for(pid: str, min_balls: int = 300) -> tuple[list[str], dict[str, list[float]]]:
    out: dict[str, list[float]] = {}
    cats = ["runs", "average", "strike_rate", "sixes", "milestones"]
    for fmt in Q.formats():  # ODI / T20 (World Cups), ODI (Champions Trophy), Test (Test Championship)
        p = V.batting_percentiles(pid, fmt, min_balls)
        if p:
            out[f"{fmt}"] = [p[c] for c in cats]
    return cats, out


if setup(
    "Player Analytics",
    "🧑",
    "Search any player: career, form, comparison with another player, consistency and role clusters.",
    ["profile", "comparison", "consistency", "clustering"],
):
    who, pid = pick_player("player", "Kohli", "a")
    # radar percentiles rank a player against everyone with at least this many balls faced in the format
    min_balls = st.sidebar.select_slider(
        "Minimum balls faced (radar)", options=MIN_BALLS_OPTIONS, value=300, key="radar_min_balls"
    )
    tabs = st.tabs(
        ["Profile", "Batting detail", "Bowling detail", "Comparison", "Consistency", "Clustering"]
    )

    with tabs[0]:
        if pid is None:
            st.warning("Search for a player in the sidebar.")
        else:
            info = V.player_info(pid)
            hist = V.player_squad_history(pid)
            bat = Q.player_batting_career(pid)
            bowl = Q.player_bowling_career(pid)
            st.subheader(who)
            cards(
                [
                    ("Role", str(info["role"] or "n/a"), str(info["teams"] or "")),
                    (
                        "Batting style",
                        str(info["batting_style"] or "n/a"),
                        f"born {str(info['date_of_birth'])[:10]}" if info["date_of_birth"] else "",
                    ),
                    ("Bowling style", str(info["bowling_style"] or "n/a"), ""),
                    ("World Cup editions", str(len(hist)), "in a squad"),
                    (
                        "Matches",
                        str(int(bat["matches"].sum())) if len(bat) else "0",
                        "with a batting record",
                    ),
                ]
            )
            a, b = st.columns(2)
            with a:
                st.markdown("**Batting career (World Cups)**")
                if len(bat):
                    st.dataframe(bat, hide_index=True, width="stretch")
                else:
                    st.caption("No batting record.")
            with b:
                st.markdown("**Bowling career (World Cups)**")
                if len(bowl):
                    st.dataframe(bowl, hide_index=True, width="stretch")
                else:
                    st.caption("No bowling record.")
            cats, series = radar_for(pid, min_balls)
            a, b = st.columns(2)
            with a:
                if series:
                    st.plotly_chart(
                        C.radar(
                            ["runs", "average", "strike rate", "sixes/inn", "milestones/inn"],
                            series,
                            f"Batting percentile vs other qualified batters (>= {min_balls} balls)",
                        ),
                        width="stretch",
                    )
                else:
                    st.info(
                        f"Not enough batting history for a percentile radar (minimum {min_balls} balls). "
                        "Lower the minimum in the filters."
                    )
            with b:
                if len(hist):
                    st.plotly_chart(
                        px.bar(
                            hist,
                            x="tournament",
                            y="matches_played",
                            color="format",
                            color_discrete_map=FORMAT_COLORS,
                            title="Matches played per edition",
                            hover_data=["team", "role", "age"],
                        ).update_layout(height=420),
                        width="stretch",
                    )
                    st.dataframe(hist, hide_index=True, width="stretch")
            coverage_note()

    with tabs[1]:
        if pid is not None:
            inn = V.player_innings_full(pid)
            if inn.empty:
                st.info("No batting innings.")
            else:
                inn = inn.reset_index(drop=True)
                inn["innings_no"] = inn.index + 1
                inn["rolling_avg"] = inn["runs"].rolling(10, min_periods=3).mean()
                inn["cumulative"] = inn["runs"].cumsum()
                a, b = st.columns(2)
                with a:
                    fig = px.scatter(
                        inn,
                        x="match_date",
                        y="runs",
                        color="format",
                        color_discrete_map=FORMAT_COLORS,
                        size="balls_faced",
                        hover_data=["opposition", "tournament", "pos"],
                        title="Every innings (size = balls faced) with 10-innings rolling average",
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=inn["match_date"],
                            y=inn["rolling_avg"],
                            mode="lines",
                            line=dict(color=TEAL, width=3),
                            name="rolling average",
                        )
                    )
                    fig.add_hline(y=50, line_dash="dot", opacity=0.4)
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, width="stretch")
                with b:
                    fig = px.area(
                        inn,
                        x="innings_no",
                        y="cumulative",
                        title="Cumulative World Cup runs",
                        color_discrete_sequence=[BLUE],
                    )
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, width="stretch")
                a, b, c = st.columns(3)
                with a:
                    st.plotly_chart(
                        px.histogram(
                            inn,
                            x="runs",
                            nbins=20,
                            color="format",
                            color_discrete_map=FORMAT_COLORS,
                            title="Score distribution",
                        ).update_layout(height=330),
                        width="stretch",
                    )
                with b:
                    pos = inn.groupby("pos", as_index=False).agg(
                        runs=("runs", "sum"), innings=("runs", "size")
                    )
                    st.plotly_chart(
                        px.bar(
                            pos,
                            x="pos",
                            y="runs",
                            text="innings",
                            title="Runs by batting position (label = innings)",
                            color_discrete_sequence=[AMBER],
                        ).update_layout(height=330),
                        width="stretch",
                    )
                with c:
                    d = V.player_dismissed_by_type(pid)
                    if len(d):
                        st.plotly_chart(
                            C.donut(
                                d["dismissal_type"], d["n"], "How he gets out (ball-by-ball)", 330
                            ),
                            width="stretch",
                        )
                    else:
                        st.caption("No ball-by-ball dismissals.")
                opp = (
                    inn.groupby("opposition", as_index=False)
                    .agg(runs=("runs", "sum"), innings=("runs", "size"), avg=("runs", "mean"))
                    .sort_values("runs")
                )
                st.plotly_chart(
                    px.bar(
                        opp,
                        x="runs",
                        y="opposition",
                        orientation="h",
                        color="avg",
                        color_continuous_scale="Tealgrn",
                        hover_data=["innings"],
                        title="Runs against each opposition (colour = average per innings)",
                    ).update_layout(height=max(320, 28 * len(opp))),
                    width="stretch",
                )
                ph = Q.player_phases(pid)
                if len(ph):
                    st.plotly_chart(
                        px.bar(
                            ph,
                            x="phase",
                            y="strike_rate",
                            color="format",
                            barmode="group",
                            color_discrete_map=FORMAT_COLORS,
                            category_orders={"phase": ["powerplay", "middle", "death"]},
                            title="Strike rate by phase (ball-by-ball matches)",
                        ).update_layout(height=340),
                        width="stretch",
                    )
                heat = inn.pivot_table(
                    index="tournament", columns="stage", values="runs", aggfunc="sum"
                )
                st.plotly_chart(
                    C.heatmap(
                        heat.to_numpy(),
                        heat.columns,
                        heat.index,
                        "Runs by tournament and stage",
                        360,
                        C.HEAT,
                        ".0f",
                    ),
                    width="stretch",
                )

    with tabs[2]:
        if pid is not None:
            bw = V.player_bowling_full(pid)
            if bw.empty:
                st.info("No bowling record for this player.")
            else:
                bw = bw.reset_index(drop=True)
                a, b = st.columns(2)
                with a:
                    fig = px.scatter(
                        bw,
                        x="match_date",
                        y="economy",
                        size="wickets",
                        color="format",
                        color_discrete_map=FORMAT_COLORS,
                        hover_data=["opposition", "tournament", "runs_conceded"],
                        title="Economy per match (size = wickets)",
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=bw["match_date"],
                            y=bw["economy"].rolling(8, min_periods=3).mean(),
                            mode="lines",
                            line=dict(color=TEAL, width=3),
                            name="rolling economy",
                        )
                    )
                    fig.update_layout(height=380)
                    st.plotly_chart(fig, width="stretch")
                with b:
                    wk = bw.groupby("tournament", as_index=False).agg(
                        wickets=("wickets", "sum"), matches=("wickets", "size")
                    )
                    st.plotly_chart(
                        px.bar(
                            wk,
                            x="tournament",
                            y="wickets",
                            text="matches",
                            title="Wickets per tournament (label = matches)",
                            color_discrete_sequence=[PINK],
                        ).update_layout(height=380),
                        width="stretch",
                    )
                a, b, c = st.columns(3)
                with a:
                    d = V.player_wickets_by_type(pid)
                    if len(d):
                        st.plotly_chart(
                            C.donut(d["dismissal_type"], d["n"], "Wickets by dismissal type", 320),
                            width="stretch",
                        )
                    else:
                        st.caption("No ball-by-ball wickets.")
                with b:
                    cnt = bw["wickets"].value_counts().sort_index().reset_index()
                    st.plotly_chart(
                        px.bar(
                            cnt,
                            x="wickets",
                            y="count",
                            title="Wickets in a match (frequency)",
                            color_discrete_sequence=[AMBER],
                        ).update_layout(height=320),
                        width="stretch",
                    )
                with c:
                    ph = V.player_bowling_phases(pid)
                    if len(ph):
                        st.plotly_chart(
                            px.bar(
                                ph,
                                x="phase",
                                y="economy",
                                color="format",
                                barmode="group",
                                color_discrete_map=FORMAT_COLORS,
                                category_orders={"phase": ["powerplay", "middle", "death"]},
                                title="Economy by phase",
                            ).update_layout(height=320),
                            width="stretch",
                        )
                    else:
                        st.caption("No ball-by-ball phases.")
                st.plotly_chart(
                    px.bar(
                        bw.groupby("opposition", as_index=False)["wickets"]
                        .sum()
                        .sort_values("wickets"),
                        x="wickets",
                        y="opposition",
                        orientation="h",
                        title="Wickets against each opposition",
                        color_discrete_sequence=[TEAL],
                    ).update_layout(height=340),
                    width="stretch",
                )

    with tabs[3]:
        who2, pid2 = pick_player("compare with", "Rohit", "b")
        if pid is None or pid2 is None:
            st.info("Pick two players in the sidebar.")
        else:
            c1, c2 = radar_for(pid, min_balls)[1], radar_for(pid2, min_balls)[1]
            fmt = st.radio("Format for the radar", Q.formats(), horizontal=True)
            series = {}
            if fmt in c1:
                series[who] = c1[fmt]
            if fmt in c2:
                series[who2] = c2[fmt]
            a, b = st.columns(2)
            with a:
                if len(series) == 2:
                    st.plotly_chart(
                        C.radar(
                            ["runs", "average", "strike rate", "sixes/inn", "milestones/inn"],
                            series,
                            f"{fmt} batting percentiles",
                        ),
                        width="stretch",
                    )
                else:
                    st.info(f"Both players need at least {min_balls} {fmt} balls faced for the radar. Lower the minimum in the filters.")
            with b:
                rows = []
                for name, p in ((who, pid), (who2, pid2)):
                    for r in A.player_career_both(p).itertuples():
                        rows.append(
                            {
                                "player": name,
                                "format": r.format,
                                "matches": r.matches,
                                "runs": r.runs,
                                "bat_avg": r.bat_avg,
                                "bat_sr": r.bat_sr,
                                "hundreds": r.hundreds,
                                "wickets": r.wickets,
                                "economy": r.economy,
                            }
                        )
                comp = pd.DataFrame(rows)
                metric = st.selectbox(
                    "Compare",
                    ["runs", "bat_avg", "bat_sr", "wickets", "economy", "hundreds", "matches"],
                )
                st.plotly_chart(
                    px.bar(
                        comp,
                        x="format",
                        y=metric,
                        color="player",
                        barmode="group",
                        title=f"{metric} by format",
                    ).update_layout(height=380),
                    width="stretch",
                )
            s1, s2 = (
                V.player_innings_full(pid).assign(player=who),
                V.player_innings_full(pid2).assign(player=who2),
            )
            both = pd.concat([s1, s2]).reset_index(drop=True)
            if len(both):
                a, b = st.columns(2)
                with a:
                    st.plotly_chart(
                        px.violin(
                            both,
                            x="player",
                            y="runs",
                            color="player",
                            box=True,
                            points="all",
                            title="Distribution of innings scores",
                        ).update_layout(height=400, showlegend=False),
                        width="stretch",
                    )
                with b:
                    cum = []
                    for name, g in both.groupby("player"):
                        g = g.sort_values("match_date").reset_index(drop=True)
                        cum.append(
                            pd.DataFrame(
                                {
                                    "player": name,
                                    "innings": g.index + 1,
                                    "cumulative runs": g["runs"].cumsum(),
                                }
                            )
                        )
                    st.plotly_chart(
                        px.line(
                            pd.concat(cum),
                            x="innings",
                            y="cumulative runs",
                            color="player",
                            title="Cumulative runs, innings by innings",
                        ).update_layout(height=400),
                        width="stretch",
                    )
            st.dataframe(comp, hide_index=True, width="stretch")

    with tabs[4]:
        st.markdown(
            "Consistency over World Cup matches. Minimum samples: **10 batting innings**, **8 bowling innings**. CV = standard deviation / mean (lower = steadier)."
        )
        bc, wc = (
            A.report_csv("model_evaluation/consistency_batting.csv"),
            A.report_csv("model_evaluation/consistency_bowling.csv"),
        )
        if bc is None:
            st.info("Run `python scripts/run_player_models.py`.")
        else:
            kind = st.radio("View", ["Batting", "Bowling"], horizontal=True)
            if kind == "Batting":
                fig = px.scatter(
                    bc,
                    x="mean_runs",
                    y="cv",
                    size="innings",
                    color="pct_30_plus",
                    color_continuous_scale="Tealgrn",
                    hover_name="player",
                    hover_data=["median_runs", "pct_ducks", "mean_ci_low", "mean_ci_high"],
                    title="Average vs consistency (bottom-right = high and steady)",
                )
                fig.update_layout(height=470)
                st.plotly_chart(fig, width="stretch")
                a, b = st.columns(2)
                with a:
                    st.plotly_chart(
                        px.histogram(
                            bc,
                            x="cv",
                            nbins=25,
                            title="Spread of batting CV",
                            color_discrete_sequence=[BLUE],
                        ).update_layout(height=320),
                        width="stretch",
                    )
                with b:
                    top = bc.nsmallest(12, "cv")
                    st.plotly_chart(
                        px.bar(
                            top.sort_values("cv", ascending=False),
                            x="cv",
                            y="player",
                            orientation="h",
                            title="Steadiest batters (lowest CV)",
                            color_discrete_sequence=[TEAL],
                        ).update_layout(height=320),
                        width="stretch",
                    )
                st.dataframe(bc.round(2), hide_index=True, width="stretch")
            else:
                fig = px.scatter(
                    wc,
                    x="mean_economy",
                    y="cv_economy",
                    size="innings",
                    color="mean_wickets",
                    color_continuous_scale="Sunsetdark",
                    hover_name="player",
                    hover_data=["pct_wicketless", "econ_ci_low", "econ_ci_high"],
                    title="Economy vs consistency (bottom-left = cheap and steady)",
                )
                fig.update_layout(height=470)
                st.plotly_chart(fig, width="stretch")
                st.dataframe(wc.round(2), hide_index=True, width="stretch")
            if who and (bc["player"] == who).any():
                st.success(
                    f"{who}: {bc.loc[bc['player'] == who].iloc[0][['innings', 'mean_runs', 'median_runs', 'cv']].round(2).to_dict()}"
                )

    with tabs[5]:
        st.markdown(
            "Player roles found by clustering (StandardScaler + K-Means; PCA only for the picture). The structure is a **continuum**, not crisp types: see the quality numbers below."
        )
        kind = st.radio("Players", ["batters", "bowlers"], horizontal=True)
        data = A.feature_parquet(f"clusters_{kind}.parquet")
        if data is None:
            st.info("Run `python scripts/run_player_models.py`.")
        else:
            a, b = st.columns(2)
            with a:
                fig = px.scatter(
                    data,
                    x="pc1",
                    y="pc2",
                    color="cluster_label",
                    hover_name="player",
                    title=f"{kind.title()} clusters (PCA projection)",
                )
                fig.update_layout(height=450)
                st.plotly_chart(fig, width="stretch")
            z = A.report_csv(f"model_evaluation/clusters_{kind}_zprofile.csv")
            labels = A.report_csv(f"model_evaluation/clusters_{kind}_labels.csv")
            with b:
                if z is not None and labels is not None:
                    lab = dict(zip(labels["cluster"], labels["label"], strict=True))
                    feats = [c for c in z.columns if c != "cluster"]
                    series = {lab.get(i, str(i)): list(z.loc[i, feats]) for i in z.index}
                    st.plotly_chart(
                        C.radar(
                            [f.replace("_", " ") for f in feats],
                            series,
                            "Cluster profiles (standardised, 0 = average player)",
                            450,
                            (-2, 2),
                        ),
                        width="stretch",
                    )
            prof = A.report_csv(f"model_evaluation/clusters_{kind}_profile.csv")
            if prof is not None and labels is not None:
                st.dataframe(
                    prof.merge(labels, on="cluster").round(2), hide_index=True, width="stretch"
                )
            sel = A.report_csv(f"model_evaluation/clusters_{kind}_k_selection.csv")
            st.plotly_chart(
                px.line(
                    sel,
                    x="k",
                    y="silhouette",
                    markers=True,
                    title="Silhouette by number of clusters (higher = better separated)",
                ).update_layout(height=300),
                width="stretch",
            )
            st.caption(
                "Silhouette about 0.2 and bootstrap stability about 0.6 mean the groups overlap; treat labels as descriptive. Labels were assigned after inspecting the profiles."
            )
            if who and (data["player"] == who).any():
                st.success(
                    f"{who} falls in: **{data.loc[data['player'] == who, 'cluster_label'].iloc[0]}**"
                )
