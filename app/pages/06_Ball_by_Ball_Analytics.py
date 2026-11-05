# ruff: noqa: E501
"""Ball-by-ball analytics: progression, over-by-over, phases, partnerships, bowlers and live projection."""

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
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils import viz_extra as X  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, RED, TEAL, cards  # noqa: E402
from app.utils.ui import coverage_note, setup  # noqa: E402
from src.ml import innings_projection as ip  # noqa: E402
from src.ml import serving  # noqa: E402

if setup(
    "Ball-by-Ball Analytics",
    "🎯",
    "Worm, Manhattan, run-rate and chase charts, scoring phases, partnerships, bowler spells and a live first-innings projection.",
    ["match selection", "innings selection", "wicket progression", "phases", "projection"],
):
    bm = Q.ball_matches()
    bm["label"] = bm["match_date"].astype(str) + "  " + bm["fixture"]
    pick = st.sidebar.selectbox("Match (ball-by-ball available)", bm["label"].tolist())
    mid = bm.loc[bm["label"] == pick, "match_id"].iloc[0]
    d = V.bbb(mid)
    tg = V.innings_targets(mid)
    inn_options = sorted(d["innings"].unique())
    inn = st.sidebar.selectbox("Innings", inn_options)
    di = d[d["innings"] == inn].copy()
    di["over_idx"] = di["over"]
    team = di["batting_team"].iloc[0]
    total = int(di["total_runs"].sum())
    wk = int(di["is_wicket"].sum())
    cards(
        [
            ("Batting", team, f"innings {inn}"),
            (
                "Score",
                f"{total}/{wk}",
                f"{di['legal_ball'].max() // 6}.{di['legal_ball'].max() % 6} overs",
            ),
            (
                "Boundaries",
                f"{int(di['is_four'].sum())} fours / {int(di['is_six'].sum())} sixes",
                "",
            ),
            ("Dot balls", f"{100 * di['is_dot_ball'].mean():.0f}%", "of deliveries"),
        ]
    )

    tabs = st.tabs(
        [
            "Run and wicket progression",
            "Over by over",
            "Scoring phases",
            "Partnerships and batters",
            "Bowlers",
            "Delivery patterns",
            "First-innings projection",
            "Deliveries",
            "Matchups",
        ]
    )

    with tabs[0]:
        a, b = st.columns(2)
        with a:
            fig = go.Figure()
            for k, g in d.groupby("innings"):
                fig.add_trace(
                    go.Scatter(
                        x=g["legal_ball"] / 6,
                        y=g["cumulative_runs"],
                        mode="lines",
                        name=f"innings {k}",
                        line=dict(width=3),
                    )
                )
                w = g[g["is_wicket"]]
                fig.add_trace(
                    go.Scatter(
                        x=w["legal_ball"] / 6,
                        y=w["cumulative_runs"],
                        mode="markers",
                        marker=dict(symbol="x", size=10, color=RED),
                        name=f"wickets (inn {k})",
                        showlegend=False,
                        text=w["batter"],
                        hoverinfo="text+y",
                    )
                )
            tgt = tg[tg["innings"] == 2]
            if len(tgt) and pd.notna(tgt["target"].iloc[0]):
                fig.add_hline(
                    y=float(tgt["target"].iloc[0]),
                    line_dash="dash",
                    line_color=AMBER,
                    annotation_text="target",
                )
            fig.update_layout(
                title="Run progression (worm), crosses = wickets",
                height=420,
                xaxis_title="overs",
                yaxis_title="runs",
            )
            st.plotly_chart(fig, width="stretch")
        with b:
            wkp = d.groupby(["innings", "over"], as_index=False)["is_wicket"].sum()
            wkp["wickets"] = wkp.groupby("innings")["is_wicket"].cumsum()
            fig = px.line(
                wkp,
                x="over",
                y="wickets",
                color=wkp["innings"].astype(str),
                line_shape="hv",
                title="Wicket progression",
            )
            fig.update_layout(height=420, legend_title_text="innings")
            st.plotly_chart(fig, width="stretch")
        if inn == 2 and len(tg) and pd.notna(tg["target"].iloc[0]):
            target = float(tg["target"].iloc[0])
            n_over = 20 if d["phase"].isin(["powerplay"]).any() and d["over"].max() <= 20 else 50
            chase = di.groupby("over", as_index=False).agg(runs=("total_runs", "sum"))
            chase["cum"] = chase["runs"].cumsum()
            chase["required_rate"] = (target - chase["cum"]) / (n_over - chase["over"]).clip(
                lower=1
            )
            chase["current_rate"] = chase["cum"] / chase["over"]
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=chase["over"],
                    y=chase["current_rate"],
                    name="current run rate",
                    line=dict(color=TEAL, width=3),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=chase["over"],
                    y=chase["required_rate"],
                    name="required run rate",
                    line=dict(color=PINK, width=3, dash="dot"),
                )
            )
            fig.update_layout(
                title=f"The chase: current vs required run rate (target {int(target)})",
                height=340,
                xaxis_title="over",
            )
            st.plotly_chart(fig, width="stretch")

    with tabs[1]:
        per = di.groupby("over", as_index=False).agg(
            runs=("total_runs", "sum"),
            wickets=("is_wicket", "sum"),
            boundaries=("is_four", "sum"),
            sixes=("is_six", "sum"),
        )
        fig = go.Figure(
            go.Bar(
                x=per["over"],
                y=per["runs"],
                marker_color=[RED if w else BLUE for w in per["wickets"] > 0],
                text=per["runs"],
                name="runs",
            )
        )
        fig.update_layout(
            title=f"Manhattan, innings {inn} (red = a wicket fell in the over)",
            height=380,
            xaxis_title="over",
        )
        st.plotly_chart(fig, width="stretch")
        a, b = st.columns(2)
        with a:
            per["run_rate_rolling"] = per["runs"].rolling(3, min_periods=1).mean()
            fig = px.area(
                per,
                x="over",
                y="run_rate_rolling",
                title="Scoring rate (3-over rolling average)",
                color_discrete_sequence=[TEAL],
            )
            fig.update_layout(height=320)
            st.plotly_chart(fig, width="stretch")
        with b:
            long = per.melt(
                id_vars="over",
                value_vars=["boundaries", "sixes"],
                var_name="type",
                value_name="count",
            )
            fig = px.bar(
                long,
                x="over",
                y="count",
                color="type",
                title="Fours and sixes by over",
                color_discrete_map={"boundaries": BLUE, "sixes": AMBER},
            )
            fig.update_layout(height=320)
            st.plotly_chart(fig, width="stretch")
        grid = di.pivot_table(index="over", columns="ball", values="total_runs", aggfunc="sum")
        st.plotly_chart(
            C.heatmap(
                grid.to_numpy(),
                [f"ball {c}" for c in grid.columns],
                grid.index,
                "Runs off each ball of each over",
                max(380, 16 * len(grid)),
                C.HEAT,
                ".0f",
            ),
            width="stretch",
        )

    with tabs[2]:
        ph = d.groupby(["innings", "phase"], as_index=False).agg(
            runs=("total_runs", "sum"),
            balls=("is_legal_ball", "sum"),
            wickets=("is_wicket", "sum"),
            dots=("is_dot_ball", "mean"),
            boundaries=("is_four", "sum"),
            sixes=("is_six", "sum"),
        )
        ph["run_rate"] = 6 * ph["runs"] / ph["balls"].clip(lower=1)
        ph["dot_pct"] = 100 * ph["dots"]
        order = ["powerplay", "middle", "death"]
        ph["innings"] = ph["innings"].astype(str)
        a, b, c = st.columns(3)
        with a:
            st.plotly_chart(
                px.bar(
                    ph,
                    x="phase",
                    y="run_rate",
                    color="innings",
                    barmode="group",
                    category_orders={"phase": order},
                    title="Run rate by phase",
                ).update_layout(height=340),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.bar(
                    ph,
                    x="phase",
                    y="wickets",
                    color="innings",
                    barmode="group",
                    category_orders={"phase": order},
                    title="Wickets by phase",
                ).update_layout(height=340),
                width="stretch",
            )
        with c:
            st.plotly_chart(
                px.bar(
                    ph,
                    x="phase",
                    y="dot_pct",
                    color="innings",
                    barmode="group",
                    category_orders={"phase": order},
                    title="Dot-ball % by phase",
                ).update_layout(height=340),
                width="stretch",
            )
        one = ph[ph["innings"] == str(inn)]
        st.plotly_chart(
            C.donut(one["phase"], one["runs"], f"Where innings {inn}'s runs came from", 340),
            width="stretch",
        )
        st.dataframe(ph.drop(columns=["dots"]).round(2), hide_index=True, width="stretch")

    with tabs[3]:
        dd = di.sort_values("delivery_sequence").copy()
        dd["partnership"] = dd["is_wicket"].shift(fill_value=False).cumsum()
        pt = dd.groupby("partnership", as_index=False).agg(
            runs=("total_runs", "sum"),
            balls=("is_legal_ball", "sum"),
            batters=("batter", lambda s: " & ".join(pd.unique(s)[:2])),
        )
        pt["wicket"] = pt["partnership"] + 1
        a, b = st.columns(2)
        with a:
            fig = px.bar(
                pt,
                x="wicket",
                y="runs",
                text="runs",
                hover_data=["batters", "balls"],
                title="Runs added for each wicket (partnerships)",
                color="runs",
                color_continuous_scale="Tealgrn",
            )
            fig.update_layout(height=380, xaxis=dict(dtick=1, title="wicket partnership"))
            st.plotly_chart(fig, width="stretch")
        with b:
            st.plotly_chart(
                C.waterfall(
                    [f"{w}" for w in pt["wicket"]],
                    pt["runs"],
                    "Innings built partnership by partnership",
                    380,
                ),
                width="stretch",
            )
        bt = di.groupby("batter", as_index=False).agg(
            runs=("batter_runs", "sum"),
            balls=("is_wide", lambda s: int((~s).sum())),
            fours=("is_four", "sum"),
            sixes=("is_six", "sum"),
        )
        bt["strike_rate"] = 100 * bt["runs"] / bt["balls"].clip(lower=1)
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.bar(
                    bt.sort_values("runs"),
                    x="runs",
                    y="batter",
                    orientation="h",
                    color="strike_rate",
                    color_continuous_scale="Tealgrn",
                    title="Runs by batter (colour = strike rate)",
                ).update_layout(height=380),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.scatter(
                    bt,
                    x="balls",
                    y="runs",
                    size=bt["fours"] + bt["sixes"] + 2,
                    color="strike_rate",
                    hover_name="batter",
                    title="Balls faced vs runs (size = boundaries)",
                    color_continuous_scale="Sunsetdark",
                ).update_layout(height=380),
                width="stretch",
            )

    with tabs[4]:
        bw = di.groupby("bowler", as_index=False).agg(
            legal=("is_legal_ball", "sum"),
            runs=("total_runs", "sum"),
            wickets=("is_wicket", "sum"),
            dots=("is_dot_ball", "sum"),
        )
        bw["overs"] = (bw["legal"] / 6).round(1)
        bw["economy"] = 6 * bw["runs"] / bw["legal"].clip(lower=1)
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                px.scatter(
                    bw,
                    x="economy",
                    y="wickets",
                    size="overs",
                    hover_name="bowler",
                    color="dots",
                    color_continuous_scale="Tealgrn",
                    title="Bowlers: economy vs wickets (size = overs, colour = dot balls)",
                ).update_layout(height=380),
                width="stretch",
            )
        with b:
            spell = di.groupby(["bowler", "over"], as_index=False)["total_runs"].sum()
            fig = px.scatter(
                spell,
                x="over",
                y="bowler",
                size=spell["total_runs"] + 1,
                color="total_runs",
                color_continuous_scale="Sunsetdark",
                title="When each bowler bowled (size and colour = runs in the over)",
            )
            fig.update_layout(height=380)
            st.plotly_chart(fig, width="stretch")
        ex = di[di["extra_runs"] > 0].groupby("extras_type", as_index=False)["extra_runs"].sum()
        if len(ex):
            st.plotly_chart(
                C.donut(ex["extras_type"].fillna("other"), ex["extra_runs"], "Extras by type", 320),
                width="stretch",
            )
        st.dataframe(
            bw.sort_values("wickets", ascending=False).round(2), hide_index=True, width="stretch"
        )

    with tabs[5]:
        a, b = st.columns(2)
        with a:
            outc = di.assign(
                outcome=np.select(
                    [
                        di["is_wicket"],
                        di["is_six"],
                        di["is_four"],
                        di["is_dot_ball"],
                        di["total_runs"] == 1,
                        di["total_runs"] == 2,
                    ],
                    ["wicket", "six", "four", "dot", "single", "two"],
                    "other",
                )
            )
            vc = outc["outcome"].value_counts()
            st.plotly_chart(
                C.donut(vc.index, vc.values, "What happens on a ball", 360), width="stretch"
            )
        with b:
            dis = di[di["is_wicket"]]["dismissal_type"].value_counts()
            if len(dis):
                st.plotly_chart(
                    C.donut(dis.index, dis.values, "How the wickets fell", 360), width="stretch"
                )
            else:
                st.info("No wickets in this innings.")
        b6 = di[(di["is_four"]) | (di["is_six"])].copy()
        b6["kind"] = np.where(b6["is_six"], "six", "four")
        if len(b6):
            fig = px.scatter(
                b6,
                x="over",
                y="batter",
                color="kind",
                symbol="kind",
                color_discrete_map={"four": BLUE, "six": AMBER},
                title="Every boundary (over and batter)",
            )
            fig.update_traces(marker=dict(size=12))
            fig.update_layout(height=max(320, 40 * b6["batter"].nunique()))
            st.plotly_chart(fig, width="stretch")
        dotrun = di.groupby("over", as_index=False).agg(
            dot_pct=("is_dot_ball", lambda s: 100 * s.mean())
        )
        st.plotly_chart(
            px.line(
                dotrun,
                x="over",
                y="dot_pct",
                markers=True,
                title="Dot-ball % by over",
                color_discrete_sequence=[PINK],
            ).update_layout(height=300),
            width="stretch",
        )

    with tabs[6]:
        st.markdown(
            "Projects the **first innings** final total from what has happened so far (linear regression on the runs still to come, evaluated out of time)."
        )
        balls = A.first_innings_balls(mid)
        if balls.empty:
            st.info("No first-innings deliveries.")
        elif balls["format"].iloc[0] not in ip.MAX_OVERS:
            st.info(
                "The live projection is trained for ODI and T20 innings only, not Test cricket."
            )
        else:
            fmt = balls["format"].iloc[0]
            n_over = ip.MAX_OVERS[fmt]
            actual = float(balls["total_runs"].sum())
            feats = A.feature_parquet("match_features.parquet")
            ctx_row = feats[feats["match_id"] == mid]
            if ctx_row.empty:
                st.info("No pre-match context for this match.")
            else:
                ctx = {c: float(ctx_row.iloc[0][c]) for c in ip.CONTEXT}
                last = int(balls["over_number"].max())
                over = st.slider(
                    "Overs completed", 3, max(min(last - 1, n_over - 1), 4), min(10, last - 1)
                )
                f = serving.innings_features_at(balls, fmt, over, ctx)
                if f is None:
                    st.warning("Not enough balls for that over.")
                else:
                    pr = serving.project_innings(f, fmt)
                    cards(
                        [
                            (
                                "Score now",
                                f"{int(f['score'])}/{int(f['wickets'])}",
                                f"after {over} overs",
                            ),
                            ("Model projection", f"{pr['model']:.0f}", "final total"),
                            (
                                "Run-rate projection",
                                f"{pr['run_rate_baseline']:.0f}",
                                "score + current rate",
                            ),
                            ("Actual final", f"{actual:.0f}", "what happened"),
                        ],
                        [TEAL, BLUE, AMBER, PINK],
                    )
                    path = []
                    for k in range(3, min(last, n_over)):
                        fk = serving.innings_features_at(balls, fmt, k, ctx)
                        if fk:
                            path.append(
                                {
                                    "over": k,
                                    "model": serving.project_innings(fk, fmt)["model"],
                                    "run-rate baseline": fk["projected_linear"],
                                }
                            )
                    if path:
                        pdf = pd.DataFrame(path).melt(
                            id_vars="over", var_name="projection", value_name="runs"
                        )
                        fig = px.line(
                            pdf,
                            x="over",
                            y="runs",
                            color="projection",
                            title="Projection as the innings unfolds",
                        )
                        fig.add_hline(
                            y=actual,
                            line_dash="dash",
                            annotation_text="actual final",
                            line_color="rgba(255,255,255,.6)",
                        )
                        fig.update_layout(height=380)
                        st.plotly_chart(fig, width="stretch")
                    met = A.report_csv("model_evaluation/innings_projection_metrics.csv")
                    if met is not None:
                        m = met[
                            (met["format"] == fmt)
                            & met["model"].isin(["baseline_run_rate", "linear_regression"])
                            & met["scope"].str.startswith("over")
                        ].copy()
                        m["over"] = m["scope"].str.replace("over ", "").astype(int)
                        st.plotly_chart(
                            px.line(
                                m,
                                x="over",
                                y="mae",
                                color="model",
                                markers=True,
                                title="Typical error (MAE, runs) by over on held-out tournaments",
                            ).update_layout(height=320),
                            width="stretch",
                        )
                        st.caption(A.projection_crossover(fmt)[1])

    with tabs[7]:
        only_w = st.checkbox("Wickets only")
        view = di.drop(columns=["over_idx"])
        st.dataframe(
            view[view["is_wicket"]] if only_w else view,
            hide_index=True,
            width="stretch",
            height=460,
        )
    with tabs[8]:
        tid_m = X.tournament_id_of(mid)
        min_m = st.select_slider(
            "Minimum balls in the matchup", options=[6, 12, 18, 24, 30], value=12, key="matchup_min_balls"
        )
        mu = X.matchups(tid_m, min_m) if tid_m else None
        if mu is None or mu.empty:
            st.info(f"No batter-bowler pair has {min_m}+ balls in this tournament: lower the minimum.")
        else:
            mu = mu.assign(strike_rate=100 * mu["runs"] / mu["balls"], dot_pct=100 * mu["dots"] / mu["balls"])
            st.caption(
                f"{len(mu)} batter-bowler pairs with at least {min_m} balls in this tournament (smaller samples are left out: "
                "a handful of balls says nothing about who has the upper hand)."
            )
            tb = mu.groupby("batter")["balls"].sum().nlargest(12).index
            tw = mu.groupby("bowler")["balls"].sum().nlargest(12).index
            hm = mu[mu["batter"].isin(tb) & mu["bowler"].isin(tw)]
            a, b = st.columns(2)
            with a:
                if hm.empty:
                    st.info("Not enough overlapping pairs for a heatmap.")
                else:
                    sr = hm.pivot_table(index="batter", columns="bowler", values="strike_rate")
                    nb = hm.pivot_table(index="batter", columns="bowler", values="balls")
                    fig = go.Figure(
                        go.Heatmap(
                            z=sr.to_numpy(),
                            x=sr.columns,
                            y=sr.index,
                            customdata=nb.reindex(index=sr.index, columns=sr.columns).to_numpy(),
                            colorscale="RdYlGn",
                            colorbar=dict(title="Strike rate"),
                            hovertemplate="%{y} v %{x}<br>strike rate %{z:.0f} off %{customdata} balls<extra></extra>",
                        )
                    )
                    fig.update_layout(
                        title=f"Batter v bowler strike rate (pairs with {min_m}+ balls; blank = fewer)",
                        height=520,
                        xaxis=dict(tickangle=-45),
                        yaxis=dict(autorange="reversed"),
                    )
                    st.plotly_chart(fig, width="stretch")
            with b:
                fig = px.scatter(
                    mu,
                    x="balls",
                    y="strike_rate",
                    size=mu["runs"].clip(lower=1),
                    color="dismissals",
                    color_continuous_scale="Reds",
                    hover_data={"batter": True, "bowler": True, "runs": True, "dismissals": True, "dot_pct": ":.0f", "balls": True},
                    size_max=28,
                    title="Every matchup: balls faced against strike rate (colour = dismissals)",
                    labels={"balls": "Balls faced", "strike_rate": "Strike rate (runs per 100 balls)"},
                )
                fig.update_layout(height=520)
                st.plotly_chart(fig, width="stretch")
            st.dataframe(
                mu.sort_values(["dismissals", "balls"], ascending=False)[["batter", "bowler", "balls", "runs", "dismissals", "strike_rate", "dot_pct", "fours", "sixes"]].round(1),
                hide_index=True,
                width="stretch",
                height=360,
            )
    coverage_note()
