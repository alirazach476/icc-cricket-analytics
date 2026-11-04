# ruff: noqa: E501
"""Data engineering for the Champions Trophy and the World Test Championship, computed live from their gold data."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import database  # noqa: E402
from app.utils.database import run  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, TEAL, cards  # noqa: E402
from app.utils.ui import setup  # noqa: E402

TABLE_NOTES = {
    "dim_teams": "one row per team",
    "dim_players": "one row per player (one id across editions)",
    "dim_venues": "cleaned ground names and cities",
    "dim_tournaments": "one row per edition (or two-year cycle)",
    "dim_dates": "calendar dimension",
    "fact_matches": "one row per match: teams, toss, result, margin, ball-by-ball flag and gap reason",
    "fact_innings": "one row per innings: runs, wickets, overs, extras split, phases, target",
    "fact_deliveries": "one row per ball bowled (Cricsheet)",
    "fact_player_performances": "player x match batting and bowling lines",
    "fact_squads": "official squads (or the playing XIs where no squad list exists)",
    "fact_super_over_performances": "super-over lines",
    "fact_tournament_standings": "points tables from ESPNcricinfo",
    "mart_batting": "batting by player and edition",
    "mart_batting_career": "batting career in this competition",
    "mart_bowling": "bowling by player and edition",
    "mart_bowling_career": "bowling career in this competition",
    "mart_data_coverage": "what is covered per edition (this page's coverage table)",
    "mart_team_performance": "team results per edition",
    "mart_tournament_summary": "one row per edition: champion, runner-up, totals",
}

# each check returns (rows checked, rows passing)
CHECKS = [
    (
        "Innings totals equal the ball-by-ball",
        "Runs per innings equal the sum of the deliveries. Penalty runs are listed outside the ball-by-ball in the source, so a difference of exactly the penalty runs is accepted.",
        "select count(*) n, count(*) filter (where i.total_runs = t.s or (coalesce(i.penalties,0) > 0 and i.total_runs - t.s = i.penalties)) ok "
        "from gold.fact_innings i join (select innings_id, sum(total_runs) s from gold.fact_deliveries group by 1) t using(innings_id) where not i.is_super_over",
    ),
    (
        "Innings wickets equal the dismissals in the ball-by-ball",
        "Wickets per innings equal the dismissal deliveries (retired hurt is not a wicket).",
        "select count(*) n, count(*) filter (where i.wickets = t.w) ok from gold.fact_innings i join (select innings_id, "
        "count(*) filter (where is_wicket and coalesce(dismissal_type,'') not in ('retired hurt','retired not out')) w from gold.fact_deliveries group by 1) t using(innings_id) where not i.is_super_over",
    ),
    (
        "Scorecard equals the innings totals",
        "Batting runs plus extras of a team in a match equal its innings total(s).",
        "select count(*) n, count(*) filter (where b.r + i.e = i.r) ok from (select match_id, batting_team_id tm, sum(total_runs) r, sum(coalesce(extras,0)) e "
        "from gold.fact_innings where not is_super_over group by 1,2) i join (select match_id, team_id tm, sum(runs) r from gold.fact_player_performances where did_bat group by 1,2) b "
        "on b.match_id = i.match_id and b.tm = i.tm",
    ),
    (
        "The winner is one of the two teams",
        "No match names a winner that did not play.",
        "select count(*) n, count(*) filter (where winner_id in (team1_id, team2_id)) ok from gold.fact_matches where winner_id is not null",
    ),
    (
        "Every match has two different teams, a date and a venue",
        "Completeness of the match header.",
        "select count(*) n, count(*) filter (where team1_id <> team2_id and match_date is not null and venue_id is not null) ok from gold.fact_matches",
    ),
    (
        "match_id is unique",
        "Primary key of fact_matches.",
        "select count(*) n, count(distinct match_id) ok from gold.fact_matches",
    ),
    (
        "delivery_id is unique",
        "Primary key of fact_deliveries.",
        "select count(*) n, count(distinct delivery_id) ok from gold.fact_deliveries",
    ),
    (
        "Every player in a performance exists in dim_players",
        "Referential integrity of player ids.",
        "select count(*) n, count(*) filter (where p.player_id is not null) ok from gold.fact_player_performances f left join gold.dim_players p using(player_id)",
    ),
    (
        "Every match venue exists in dim_venues",
        "Referential integrity of venue ids.",
        "select count(*) n, count(*) filter (where v.venue_id is not null) ok from gold.fact_matches m left join gold.dim_venues v using(venue_id)",
    ),
]

LINEAGE = """digraph G {
  rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef3fb", color="#0fa896", fontname="Helvetica", fontsize=11]; edge [color="#e8a317"];
  espn [label="ESPNcricinfo\\nschedule, scorecards,\\nsquads, points tables"]; cs [label="Cricsheet\\nball-by-ball JSON"];
  cfg [label="config\\ncompetitions.yaml\\nawards, overrides"];
  raw [label="data/raw\\nas collected\\n(sha256 manifest)"]; silver [label="Silver\\nmatches, innings,\\ndeliveries, players"];
  gold [label="Gold\\ndimensions, facts, marts"]; duck [label="DuckDB\\none file per competition"]; app [label="Dashboard\\nFastAPI + React"];
  espn -> raw; cs -> raw; raw -> silver; cfg -> silver; silver -> gold; gold -> duck; duck -> app;
}"""

if setup(
    "Data Engineering",
    "🛠️",
    "Where this competition's data comes from, how it was built, what is covered, and the checks that prove the numbers add up.",
    ["sources", "coverage", "tables", "quality checks", "lineage"],
):
    comp = database.competition()
    is_test = comp == "wtc"
    name = "World Test Championship" if is_test else "Champions Trophy"
    cov = run("select * from gold.mart_data_coverage order by year")
    tables = run(
        "select table_name from information_schema.tables where table_schema = 'gold' order by 1"
    )["table_name"].tolist()
    counts = {t: int(run(f"select count(*) n from gold.{t}").iloc[0, 0]) for t in tables}
    played = int(cov["played_matches"].sum())
    bbb = int(cov["played_with_ball_by_ball"].sum())
    cards(
        [
            ("Matches", f"{int(cov['matches'].sum()):,}", f"{len(cov)} editions"),
            ("Ball-by-ball", f"{bbb} of {played}", f"{100 * bbb / max(played, 1):.0f}% of played matches"),
            ("Deliveries", f"{counts.get('fact_deliveries', 0):,}", "one row per ball"),
            ("Players", f"{counts.get('dim_players', 0):,}", "one id across editions"),
        ]
    )
    only_espn = "none: every played Test has ball-by-ball" if is_test else "abandoned matches and the 2002 edition, which has no open ball-by-ball"
    tabs = st.tabs(["Sources and pipeline", "Coverage", "Tables", "Quality checks", "Lineage"])

    with tabs[0]:
        st.markdown(
            f"""
**How the {name} data was built**

1. **Download.** The two open Cricsheet archives (ball-by-ball JSON) are downloaded once and fingerprinted (sha256 manifest).
2. **Collect.** The project's own collector (identifying user agent, robots.txt respected, throttling, a hard stop on 401, 403 and 429) fetches ESPNcricinfo schedules, points tables, squads and scorecards for every edition. Raw HTML is kept as collected; parsed JSON is written beside it.
3. **Silver.** Cricsheet matches are converted to the same schema as the World Cup tables. Player names are resolved against the match's own ESPNcricinfo roster, so one player has one id. Matches that only ESPNcricinfo has ({only_espn}) become scorecard-only matches.
4. **Gold.** The same dimension, fact and mart tables as the World Cups, built by the shared gold builder (with Test support: phases, the last innings as the chase, draws, penalty runs).
5. **DuckDB.** One file for this competition, identical schema, read-only for the dashboard.

Every step is re-runnable from the raw files: `python scripts/run_competitions.py`.
"""
        )
        src = pd.DataFrame(
            [
                ["Schedule, results, standings, squads, scorecards", "ESPNcricinfo", "complete (every match, incl. abandoned)"],
                ["Every ball bowled", "Cricsheet", f"{bbb} of {played} played matches"],
                ["Player of the tournament" if not is_test else "Player of the final", "config/competition_awards.csv (supplied by the project owner)", "every edition"],
                ["Cycle membership" if is_test else "Joint winners (2002)", "ESPNcricinfo series schedule" if is_test else "config/competitions.yaml", "explicit, not guessed"],
            ],
            columns=["Data", "Source", "Coverage"],
        )
        st.dataframe(src, hide_index=True, width="stretch")
        st.caption(
            "Nothing is fabricated: where a source has no data (for example ball-by-ball for 2002), the match is kept as scorecard-only and the gap reason is stored in fact_matches."
        )

    with tabs[1]:
        show = cov[
            [
                "tournament_name",
                "matches",
                "played_matches",
                "no_result_or_abandoned",
                "played_with_ball_by_ball",
                "played_without_ball_by_ball",
                "ball_by_ball_coverage_pct_of_played",
                "teams",
                "teams_with_squad",
            ]
        ].rename(
            columns={
                "tournament_name": "edition",
                "played_matches": "played",
                "no_result_or_abandoned": "abandoned / no result",
                "played_with_ball_by_ball": "with ball-by-ball",
                "played_without_ball_by_ball": "scorecard only",
                "ball_by_ball_coverage_pct_of_played": "ball-by-ball %",
                "teams_with_squad": "teams with squad",
            }
        )
        st.dataframe(show, hide_index=True, width="stretch")
        label = cov["tournament_name"].str.replace("ICC ", "", regex=False)
        fig = go.Figure()
        fig.add_bar(x=label, y=cov["played_with_ball_by_ball"], name="played, with ball-by-ball", marker_color=TEAL)
        fig.add_bar(x=label, y=cov["played_without_ball_by_ball"], name="played, scorecard only", marker_color=AMBER)
        fig.add_bar(x=label, y=cov["no_result_or_abandoned"], name="abandoned / no result", marker_color=PINK)
        fig.update_layout(barmode="stack", title="What each edition contains", yaxis_title="Matches", height=380, legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, width="stretch")
        gaps = run(
            "select ball_by_ball_gap_reason reason, count(*) matches from gold.fact_matches where not has_ball_by_ball group by 1 order by 2 desc"
        )
        if len(gaps):
            st.markdown("**Why a match has no ball-by-ball**")
            st.dataframe(gaps, hide_index=True, width="stretch")

    with tabs[2]:
        rows = pd.DataFrame(
            [[t, counts[t], TABLE_NOTES.get(t, "")] for t in tables], columns=["table", "rows", "what it holds"]
        )
        st.dataframe(rows, hide_index=True, width="stretch")
        fig = go.Figure(go.Bar(x=rows["rows"], y=rows["table"], orientation="h", marker_color=BLUE, hovertemplate="%{y}: %{x:,} rows<extra></extra>"))
        fig.update_layout(title="Rows per gold table", height=520, xaxis_type="log", xaxis_title="Rows (log scale)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")

    with tabs[3]:
        res = []
        for title, why, sql in CHECKS:
            r = run(sql).iloc[0]
            n, ok = int(r["n"]), int(r["ok"])
            res.append({"check": title, "rows checked": n, "passed": ok, "pass %": round(100 * ok / max(n, 1), 2), "status": "pass" if ok == n else "see note", "what it proves": why})
        df = pd.DataFrame(res)
        total, passed = int(df["rows checked"].sum()), int(df["passed"].sum())
        cards(
            [
                ("Checks", str(len(df)), "reconciliation, keys, integrity"),
                ("Rows checked", f"{total:,}", "across all checks"),
                ("Passing", f"{100 * passed / max(total, 1):.2f}%", f"{total - passed} rows to explain"),
            ]
        )
        st.dataframe(df, hide_index=True, width="stretch")
        failing = df[df["status"] != "pass"]
        if len(failing):
            names = "; ".join(
                f"{r['check']} ({int(r['rows checked']) - int(r['passed'])} of {int(r['rows checked']):,})"
                for _, r in failing.iterrows()
            )
            st.warning(f"Rows that do not pass are shown, not hidden: {names}.")
        st.caption(
            "These run live against the gold tables each time the page opens. Primary and foreign keys are also enforced when the data is loaded."
        )

    with tabs[4]:
        st.graphviz_chart(LINEAGE)
        st.caption("Gold is built by the same code for every competition, so the dashboard pages are shared.")
