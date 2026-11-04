# ruff: noqa: E501
"""Historical records: hall of fame cards and the SQL analytics library, run live with automatic charts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils.database import run  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, TEAL, cards  # noqa: E402
from app.utils.ui import setup  # noqa: E402

if setup(
    "Historical Records",
    "📜",
    "Records and leaderboards, plus the full SQL analytics library run live with automatic charts.",
    ["hall of fame", "40 SQL queries", "live"],
):
    tabs = st.tabs(["Hall of fame", "Query explorer"])

    with tabs[0]:
        hs = run(
            "select p.full_name player, f.runs, f.balls_faced, f.year, o.team_name opp from gold.fact_player_performances f join gold.dim_players p using(player_id) join gold.dim_teams o on o.team_id = f.opposition_team_id where f.did_bat order by f.runs desc limit 1"
        ).iloc[0]
        bb = run(
            "select p.full_name player, f.wickets, f.runs_conceded, f.year from gold.fact_player_performances f join gold.dim_players p using(player_id) where f.did_bowl order by f.wickets desc, f.runs_conceded limit 1"
        ).iloc[0]
        ht = run(
            "select batting_team team, total_runs, year, bowling_team opp from gold.fact_innings where not is_super_over order by total_runs desc limit 1"
        ).iloc[0]
        lt = run(
            "select batting_team team, total_runs, year from gold.fact_innings where not is_super_over and wickets = 10 order by total_runs limit 1"
        ).iloc[0]
        bw = run(
            "select winner_name, loser_id, margin_value, year from gold.fact_matches where margin_type = 'runs' order by margin_value desc limit 1"
        ).iloc[0]
        cards(
            [
                (
                    "Highest score",
                    f"{int(hs['runs'])}",
                    f"{hs['player']} v {hs['opp']} ({int(hs['year'])})",
                ),
                (
                    "Best bowling",
                    f"{int(bb['wickets'])}/{int(bb['runs_conceded'])}",
                    f"{bb['player']} ({int(bb['year'])})",
                ),
                (
                    "Highest total",
                    f"{int(ht['total_runs'])}",
                    f"{ht['team']} v {ht['opp']} ({int(ht['year'])})",
                ),
                ("Lowest all-out", f"{int(lt['total_runs'])}", f"{lt['team']} ({int(lt['year'])})"),
                (
                    "Biggest win (runs)",
                    f"{int(bw['margin_value'])}",
                    f"{bw['winner_name']} ({int(bw['year'])})",
                ),
            ],
            [TEAL, PINK, BLUE, AMBER, "#9B7BFF"],
        )
        a, b = st.columns(2)
        with a:
            d = run(
                "select p.full_name player, f.runs, f.balls_faced, f.format, f.year from gold.fact_player_performances f join gold.dim_players p using(player_id) where f.did_bat order by f.runs desc limit 15"
            )
            st.plotly_chart(
                px.bar(
                    d.sort_values("runs"),
                    x="runs",
                    y="player",
                    orientation="h",
                    color="format",
                    hover_data=["balls_faced", "year"],
                    title="Highest individual scores",
                ).update_layout(height=450),
                width="stretch",
            )
        with b:
            d = run(
                "select p.full_name player, f.wickets, f.runs_conceded, f.format, f.year from gold.fact_player_performances f join gold.dim_players p using(player_id) where f.did_bowl order by f.wickets desc, f.runs_conceded limit 15"
            )
            st.plotly_chart(
                px.bar(
                    d.sort_values("wickets"),
                    x="wickets",
                    y="player",
                    orientation="h",
                    color="runs_conceded",
                    color_continuous_scale="Tealgrn_r",
                    hover_data=["year", "format"],
                    title="Best bowling figures (colour = runs conceded)",
                ).update_layout(height=450),
                width="stretch",
            )
        a, b = st.columns(2)
        with a:
            d = run(
                "select batting_team team, total_runs, year, format from gold.fact_innings where not is_super_over order by total_runs desc limit 15"
            )
            st.plotly_chart(
                px.bar(
                    d.assign(label=d["team"] + " " + d["year"].astype(str)).sort_values(
                        "total_runs"
                    ),
                    x="total_runs",
                    y="label",
                    orientation="h",
                    color="format",
                    title="Highest team totals",
                ).update_layout(height=450),
                width="stretch",
            )
        with b:
            d = run(
                "select winner_name, margin_value, year, format from gold.fact_matches where margin_type = 'runs' order by margin_value desc limit 15"
            )
            st.plotly_chart(
                px.bar(
                    d.assign(label=d["winner_name"] + " " + d["year"].astype(str)).sort_values(
                        "margin_value"
                    ),
                    x="margin_value",
                    y="label",
                    orientation="h",
                    color="format",
                    title="Biggest wins by runs",
                ).update_layout(height=450),
                width="stretch",
            )
        st.caption("ODI data starts at the 2003 World Cup, so career records cover 2003-2023 only.")

    with tabs[1]:
        lib = Q.parse_library()
        groups = sorted({q["group"] for q in lib})
        group = st.sidebar.selectbox("Topic", groups)
        items = [q for q in lib if q["group"] == group]
        pick = st.sidebar.selectbox("Question", [q["question"] for q in items])
        q = next(i for i in items if i["question"] == pick)
        st.subheader(q["question"])
        try:
            df = run(q["sql"])
        except Exception as exc:  # noqa: BLE001 - e.g. dbt tables not built
            df = None
            st.warning(
                f"This query needs the dbt models (`dbt build --project-dir dbt_gold --profiles-dir dbt_gold`): {exc}"
            )
        if df is not None and len(df):
            num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            txt = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
            if num and txt and len(df) <= 60:
                y = st.selectbox("Chart value", num, index=0)
                lab = (
                    df[txt[0]].astype(str)
                    if len(txt) == 1
                    else df[txt[:2]].astype(str).agg(" | ".join, axis=1)
                )
                d = df.assign(label=lab).sort_values(y)
                st.plotly_chart(
                    px.bar(
                        d,
                        x=y,
                        y="label",
                        orientation="h",
                        color=y,
                        color_continuous_scale="Tealgrn",
                    ).update_layout(height=max(320, 22 * len(d))),
                    width="stretch",
                )
            elif "year" in df.columns and num:
                y = st.selectbox("Chart value", [c for c in num if c != "year"] or num)
                color = "format" if "format" in df.columns else None
                st.plotly_chart(
                    px.line(df, x="year", y=y, color=color, markers=True).update_layout(height=380),
                    width="stretch",
                )
            st.dataframe(df, hide_index=True, width="stretch")
        with st.expander("SQL"):
            st.code(q["sql"], language="sql")
        st.caption("ODI data starts at the 2003 World Cup, so career records cover 2003-2023 only.")
