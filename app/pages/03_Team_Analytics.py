# ruff: noqa: E501
"""Team analytics: history, strength (Elo), batting/bowling, comparison, head-to-head, players."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils import viz_data as V  # noqa: E402
from app.utils.theme import AMBER, BLUE, TEAL, cards, flag  # noqa: E402
from app.utils.ui import setup  # noqa: E402

STAGE_DEPTH = {
    "First Round": 1,
    "Group Stage": 1,
    "Super Six": 2,
    "Super Eight": 2,
    "Super Ten": 2,
    "Super 12": 2,
    "Quarterfinal": 3,
    "Semifinal": 4,
    "Final": 5,
}
DEPTH_LABEL = {
    1: "group / first round",
    2: "super stage",
    3: "quarter-final",
    4: "semi-final",
    5: "final",
}

if setup(
    "Team Analytics",
    "🌍",
    "History, strength, batting and bowling, comparison and head-to-head for every team.",
    ["Elo ratings", "radar comparison", "head-to-head"],
):
    teams = Q.teams()
    names = teams["team_name"].tolist()
    ix = lambda n: names.index(n) if n in names else 0  # noqa: E731
    name = st.sidebar.selectbox("Team", names, index=ix("India"))
    other = st.sidebar.selectbox("Compare with", names, index=ix("Australia"))
    tid = teams.loc[teams["team_name"] == name, "team_id"].iloc[0]
    oid = teams.loc[teams["team_name"] == other, "team_id"].iloc[0]
    tabs = st.tabs(
        [
            "World Cup history",
            "Strength and Elo",
            "Batting and bowling",
            "Comparison",
            "Head-to-head",
            "Players",
        ]
    )

    with tabs[0]:
        rec = Q.team_record(tid)
        st.subheader(f"{flag(name)} {name}")
        if rec.empty:
            st.info("No tournament record.")
        else:
            cards(
                [
                    ("Editions", str(len(rec)), "World Cups played"),
                    ("Titles", str(int(rec["champion"].sum())), "champion"),
                    ("Matches", str(int(rec["matches"].sum())), "all editions"),
                    (
                        "Win %",
                        f"{100 * rec['wins'].sum() / max(rec['matches'].sum(), 1):.1f}",
                        "of matches played",
                    ),
                ]
            )
            a, b = st.columns(2)
            with a:
                st.plotly_chart(
                    px.bar(
                        rec,
                        x="tournament",
                        y="win_pct",
                        color="champion",
                        title="Win % by edition",
                        color_discrete_map={True: AMBER, False: "#4C8DFF"},
                    ).update_layout(height=380),
                    width="stretch",
                )
            with b:
                prog = rec.assign(depth=rec["furthest"].map(STAGE_DEPTH))
                fig = px.line(
                    prog,
                    x="tournament",
                    y="depth",
                    markers=True,
                    title="How far they went",
                    hover_data=["furthest"],
                )
                fig.update_traces(
                    line_shape="hv", line=dict(width=3, color=TEAL), marker=dict(size=11)
                )
                fig.update_yaxes(
                    tickmode="array",
                    tickvals=list(DEPTH_LABEL),
                    ticktext=list(DEPTH_LABEL.values()),
                )
                fig.update_layout(height=380)
                st.plotly_chart(fig, width="stretch")
            st.dataframe(rec, hide_index=True, width="stretch")

    with tabs[1]:
        fmt = st.radio("Format", Q.formats(), horizontal=True, key="fmt_elo")
        elo = V.elo_history(fmt)
        if elo.empty:
            st.info("Run the feature pipeline for Elo ratings.")
        else:
            latest = (
                elo.sort_values("match_date")
                .groupby("team", as_index=False)
                .last()
                .sort_values("elo")
            )
            default = latest.nlargest(6, "elo")["team"].tolist()
            if name in elo["team"].unique() and name not in default:
                default = [*default[:5], name]
            pick = st.multiselect("Teams", sorted(elo["team"].unique()), default=default)
            sel = elo[elo["team"].isin(pick)]
            fig = px.line(
                sel,
                x="match_date",
                y="elo",
                color="team",
                title=f"{fmt} Elo rating before each match",
            )
            fig.update_layout(height=430)
            st.plotly_chart(fig, width="stretch")
            a, b = st.columns(2)
            with a:
                latest["label"] = latest["team"].map(flag) + " " + latest["team"]
                st.plotly_chart(
                    px.bar(
                        latest,
                        x="elo",
                        y="label",
                        orientation="h",
                        color="elo",
                        color_continuous_scale="Tealgrn",
                        title="Rating going into each team's latest match",
                    ).update_layout(
                        height=max(380, 24 * len(latest)),
                        xaxis=dict(range=[1300, latest["elo"].max() + 40]),
                    ),
                    width="stretch",
                )
            with b:
                ym = V.team_year_matrix(fmt).pivot_table(
                    index="team", columns="year", values="win_pct"
                )
                st.plotly_chart(
                    C.heatmap(
                        ym.to_numpy(),
                        ym.columns,
                        ym.index,
                        f"{fmt}: win % by team and edition",
                        max(380, 24 * len(ym)),
                        C.DIVERGING,
                        ".0f",
                        zmid=50,
                    ),
                    width="stretch",
                )
            summ = V.team_summary_all()
            ss = summ[(summ["format"] == fmt) & (summ["matches"] >= 10)]
            fig = px.scatter(
                ss,
                x="runs_scored",
                y="runs_conceded",
                size="matches",
                color="win_pct",
                color_continuous_scale="RdYlGn",
                text="team",
                title=f"{fmt}: runs scored vs conceded per innings (size = matches, colour = win %)",
            )
            fig.update_traces(textposition="top center", textfont=dict(size=9))
            fig.update_yaxes(autorange="reversed")
            fig.update_layout(height=470)
            st.plotly_chart(fig, width="stretch")
            st.caption("Top-left is the best place to be: score a lot, concede little.")

    with tabs[2]:
        sc = A.team_scoring(tid)
        if sc.empty:
            st.info("No data.")
        else:
            long = sc.melt(
                id_vars=["tournament", "year", "format"],
                value_vars=["avg_runs_scored", "avg_runs_conceded"],
                var_name="measure",
                value_name="runs",
            )
            a, b = st.columns(2)
            with a:
                st.plotly_chart(
                    px.line(
                        long,
                        x="year",
                        y="runs",
                        color="measure",
                        line_dash="format",
                        markers=True,
                        title=f"{name}: average runs scored and conceded per innings",
                    ).update_layout(height=380),
                    width="stretch",
                )
            with b:
                bf = sc.melt(
                    id_vars=["tournament", "year", "format"],
                    value_vars=["wins_batting_first", "wins_chasing"],
                    var_name="how",
                    value_name="wins",
                )
                st.plotly_chart(
                    px.bar(
                        bf,
                        x="tournament",
                        y="wins",
                        color="how",
                        barmode="stack",
                        title="Wins by batting first vs chasing",
                        color_discrete_map={"wins_batting_first": BLUE, "wins_chasing": AMBER},
                    ).update_layout(height=380),
                    width="stretch",
                )
            a, b = st.columns(2)
            with a:
                tv = V.team_venues(tid)
                tv["win_pct"] = 100 * tv["wins"] / tv["matches"]
                st.plotly_chart(
                    px.bar(
                        tv.sort_values("matches"),
                        x="matches",
                        y="venue_name",
                        orientation="h",
                        color="win_pct",
                        color_continuous_scale="RdYlGn",
                        range_color=[0, 100],
                        title="Record at their busiest venues (colour = win %)",
                    ).update_layout(height=430),
                    width="stretch",
                )
            with b:
                tt = V.team_toss(tid)
                if len(tt):
                    labels = [f"won toss, chose {r.toss_decision}" for r in tt.itertuples()]
                    st.plotly_chart(
                        C.sankey(
                            sorted(set(labels)) + ["won match", "did not win"],
                            [sorted(set(labels)).index(lbl) for lbl in labels],
                            [
                                len(set(labels)) + (0 if r.result == "won match" else 1)
                                for r in tt.itertuples()
                            ],
                            tt["n"].tolist(),
                            "When they win the toss",
                            430,
                        ),
                        width="stretch",
                    )
            st.dataframe(A.team_summary(tid), hide_index=True, width="stretch")
            st.caption(
                "Averages are per completed innings in scorecard matches (not DLS-affected)."
            )

    with tabs[3]:
        summ = V.team_summary_all()
        fmt = st.radio("Format", Q.formats(), horizontal=True, key="fmt_cmp")
        s = summ[(summ["format"] == fmt) & (summ["matches"] >= 10)].copy()
        if (s["team"] == name).any() and (s["team"] == other).any():
            s["bat_first_share"] = s["wins_bat_first"] / (
                s["wins_bat_first"] + s["wins_chasing"]
            ).clip(lower=1)
            metrics = {
                "win_pct": "win %",
                "runs_scored": "runs scored",
                "runs_conceded": "runs conceded (inverse)",
                "titles": "titles",
                "editions": "editions",
                "bat_first_share": "wins batting first",
            }
            norm = pd.DataFrame(index=s["team"])
            for m_ in metrics:
                v = s.set_index("team")[m_].astype(float)
                rng = (v.max() - v.min()) or 1.0
                norm[m_] = 100 * (v - v.min()) / rng
            norm["runs_conceded"] = 100 - norm["runs_conceded"]
            a, b = st.columns([3, 2])
            with a:
                st.plotly_chart(
                    C.radar(
                        list(metrics.values()),
                        {name: norm.loc[name].tolist(), other: norm.loc[other].tolist()},
                        f"{fmt}: {name} vs {other} (scaled across teams with 10+ matches)",
                    ),
                    width="stretch",
                )
            with b:
                st.dataframe(
                    s[s["team"].isin([name, other])].drop(columns=["bat_first_share"]),
                    hide_index=True,
                    width="stretch",
                )
                long = s[s["team"].isin([name, other])].melt(
                    id_vars="team",
                    value_vars=["wins", "matches"],
                    var_name="measure",
                    value_name="n",
                )
                st.plotly_chart(
                    px.bar(long, x="measure", y="n", color="team", barmode="group").update_layout(
                        height=300
                    ),
                    width="stretch",
                )
        else:
            st.info(f"Both teams need 10+ {fmt} matches for the radar.")

    with tabs[4]:
        pair = A.team_pair_record(tid, oid)
        if pair.empty:
            st.info(f"{name} and {other} have not met in a World Cup.")
        else:
            wins = pair["winner"].value_counts()
            cards(
                [
                    (f"{flag(name)} {name} wins", str(int(wins.get(name, 0))), ""),
                    (f"{flag(other)} {other} wins", str(int(wins.get(other, 0))), ""),
                    ("No winner", str(int(pair["winner"].isna().sum())), "tie / no result"),
                ],
                [BLUE, AMBER, "#8FA0C0"],
            )
            pair = pair.assign(
                winner_label=pair["winner"].fillna("no result"),
                size=pair["margin_value"].fillna(5).clip(lower=3),
            )
            st.plotly_chart(
                px.scatter(
                    pair,
                    x="match_date",
                    y="format",
                    color="winner_label",
                    size="size",
                    hover_data=["stage", "margin_type", "margin_value"],
                    title="Every meeting",
                ).update_layout(height=300),
                width="stretch",
            )
            st.dataframe(
                pair.drop(columns=["winner_label", "size"]), hide_index=True, width="stretch"
            )
        opp = V.team_vs_opponents(tid)
        a, b = st.columns(2)
        with a:
            st.plotly_chart(
                C.diverging_bar(
                    opp[opp["matches"] >= 2],
                    "opponent",
                    "win_pct",
                    f"{name}: win % against each opponent (2+ meetings)",
                    460,
                ),
                width="stretch",
            )
        with b:
            st.plotly_chart(
                px.treemap(
                    opp,
                    path=["opponent"],
                    values="matches",
                    color="win_pct",
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 100],
                    title="Opponents by number of meetings (colour = win %)",
                ).update_layout(height=460, margin=dict(l=4, r=4, t=50, b=4)),
                width="stretch",
            )
        st.caption(
            "Matches with no winner (ties, no results, abandoned) count in 'matches' but in neither wins nor losses."
        )

    with tabs[5]:
        a, b = st.columns(2)
        with a:
            tb = V.team_top_batters(tid)
            st.plotly_chart(
                px.bar(
                    tb.sort_values("runs"),
                    x="runs",
                    y="player",
                    orientation="h",
                    color="average",
                    color_continuous_scale="Tealgrn",
                    title=f"{name}: leading run scorers",
                ).update_layout(height=430),
                width="stretch",
            )
        with b:
            tw = V.team_top_bowlers(tid)
            st.plotly_chart(
                px.bar(
                    tw.sort_values("wickets"),
                    x="wickets",
                    y="player",
                    orientation="h",
                    color="economy",
                    color_continuous_scale="Sunsetdark",
                    title=f"{name}: leading wicket takers",
                ).update_layout(height=430),
                width="stretch",
            )
        st.caption("See the Squads page for the full squad lists, roles and ages.")
