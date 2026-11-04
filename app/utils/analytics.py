# ruff: noqa: E501
"""Extra dashboard data access: aggregates for the analytics pages and the saved model/report outputs."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app.utils.database import PROJECT_ROOT, run

REPORTS = PROJECT_ROOT / "reports"
FEATURES = PROJECT_ROOT / "data" / "features"


# ------------------------------------------------------------------ report files
@st.cache_data(ttl=600, show_spinner=False)
def report_csv(rel: str) -> pd.DataFrame | None:
    path = REPORTS / rel
    return pd.read_csv(path) if path.exists() else None


@st.cache_data(ttl=600, show_spinner=False)
def feature_parquet(name: str) -> pd.DataFrame | None:
    path = FEATURES / name
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except ImportError:  # slim deployments ship without pyarrow: DuckDB reads parquet natively
        import duckdb

        con = duckdb.connect()
        try:
            return con.execute("select * from read_parquet(?)", [str(path)]).fetchdf()
        finally:
            con.close()


def report_json(rel: str) -> dict | None:
    path = REPORTS / rel
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def data_quality_score() -> float | None:
    from app.utils import database

    if database.competition() != "wc":
        return None  # the quality rules were run on the World Cup gold layer only
    d = report_csv("gold/data_quality/dataset_scores.csv")
    return None if d is None else float(d["overall"].mean())


# ------------------------------------------------------------------ home
def totals() -> pd.Series:
    return run(
        "select (select count(*) from gold.dim_tournaments) tournaments, "
        "(select count(*) from gold.fact_matches) matches, "
        "(select count(*) from gold.dim_teams) teams, "
        "(select count(*) from gold.dim_players) players, "
        "(select sum(total_runs) from gold.fact_innings where not is_super_over) runs, "
        "(select sum(wickets) from gold.fact_innings where not is_super_over) wickets, "
        "(select sum(played_with_ball_by_ball) * 100.0 / sum(played_matches) from gold.mart_data_coverage) bbb_pct"
    ).iloc[0]


# ------------------------------------------------------------------ tournaments
def awards(tid: str) -> pd.DataFrame:
    return run(
        "select 'Champion' as award, t.team_name as recipient from gold.dim_tournaments d "
        "join gold.dim_teams t on t.team_id = d.winner_team_id where d.tournament_id = ? "
        "union all select 'Runner-up', t.team_name from gold.dim_tournaments d "
        "join gold.dim_teams t on t.team_id = d.runner_up_team_id where d.tournament_id = ? "
        "union all select 'Player of the Tournament', p.full_name from gold.dim_tournaments d "
        "join gold.dim_players p on p.player_id = d.player_of_tournament_id where d.tournament_id = ?",
        (tid, tid, tid),
    )


def player_of_match_leaders(tid: str, n: int = 8) -> pd.DataFrame:
    return run(
        "select p.full_name as player, count(*) as awards from gold.fact_matches m "
        "join gold.dim_players p on p.player_id = m.player_of_match_id where m.tournament_id = ? "
        "group by 1 order by 2 desc, 1 limit ?",
        (tid, n),
    )


def stage_stats(tid: str) -> pd.DataFrame:
    return run(
        "select stage, count(*) as matches, round(avg(first_innings_runs), 1) as avg_first_innings, "
        "round(avg(second_innings_runs), 1) as avg_second_innings, "
        "round(100.0 * count(*) filter (where winner_id = batting_first_team_id) / "
        "nullif(count(*) filter (where winner_id is not null), 0), 1) as bat_first_win_pct "
        "from gold.fact_matches where tournament_id = ? and is_completed and not is_walkover "
        "group by stage order by min(match_date)",
        (tid,),
    )


# ------------------------------------------------------------------ matches
def toss_by_year() -> pd.DataFrame:
    return run(
        "select format, year, count(*) as matches, "
        "round(100.0 * count(*) filter (where toss_decision = 'field') / count(*), 1) as chose_field_pct, "
        "round(100.0 * count(*) filter (where winner_id = toss_winner_id) / "
        "nullif(count(*) filter (where winner_id is not null), 0), 1) as toss_winner_win_pct "
        "from gold.fact_matches where toss_winner_id is not null and is_completed group by 1, 2 order by 1, 2"
    )


def toss_decision_outcome() -> pd.DataFrame:
    return run(
        "select format, toss_decision, count(*) as matches, "
        "round(100.0 * count(*) filter (where winner_id = toss_winner_id) / count(*), 1) as toss_winner_win_pct "
        "from gold.fact_matches where toss_decision is not null and winner_id is not null and toss_winner_id is not null "
        "group by 1, 2 order by 1, 2"
    )


def bat_first_vs_chase() -> pd.DataFrame:
    return run(
        "select format, year, count(*) as matches, "
        "count(*) filter (where winner_id = batting_first_team_id) as bat_first_wins, "
        "count(*) filter (where winner_id = batting_second_team_id) as chase_wins "
        "from gold.fact_matches where is_completed and not is_walkover and winner_id is not null "
        "group by 1, 2 order by 1, 2"
    )


def margins() -> pd.DataFrame:
    return run(
        "select format, margin_type, margin_value from gold.fact_matches where margin_type in ('runs', 'wickets')"
    )


def format_comparison() -> pd.DataFrame:
    return run(
        "select format, sum(matches) as matches, round(sum(total_runs) * 1.0 / sum(matches), 1) as runs_per_match, "
        "round(avg(avg_first_innings_score), 1) as avg_first_innings, round(sum(sixes) * 1.0 / sum(matches), 1) as sixes_per_match, "
        "round(sum(fours) * 1.0 / sum(matches), 1) as fours_per_match, round(avg(bat_first_win_pct), 1) as bat_first_win_pct "
        "from gold.mart_tournament_summary group by format order by format"
    )


def trends() -> pd.DataFrame:
    return run(
        "select format, year, runs_per_match, avg_first_innings_score, sixes * 1.0 / matches as sixes_per_match, "
        "bat_first_win_pct from gold.mart_tournament_summary order by format, year"
    )


# ------------------------------------------------------------------ players
def player_career_both(pid: str) -> pd.DataFrame:
    return run(
        "select b.format, b.matches, b.runs, b.average as bat_avg, b.strike_rate as bat_sr, b.hundreds, b.fifties, "
        "w.wickets, w.economy, w.average as bowl_avg, w.best_figures "
        "from gold.mart_batting_career b left join gold.mart_bowling_career w using (player_id, format) where b.player_id = ? "
        "union all select w.format, w.matches, null, null, null, null, null, w.wickets, w.economy, w.average, w.best_figures "
        "from gold.mart_bowling_career w where w.player_id = ? and not exists "
        "(select 1 from gold.mart_batting_career b where b.player_id = w.player_id and b.format = w.format)",
        (pid, pid),
    )


def player_innings(pid: str) -> pd.DataFrame:
    return run(
        "select f.match_date, f.year, f.format, f.runs, f.balls_faced, f.batting_position as pos, f.is_out "
        "from gold.fact_player_performances f where f.player_id = ? and f.did_bat and f.runs is not null order by f.match_date",
        (pid,),
    )


# ------------------------------------------------------------------ teams
def team_pair_record(a: str, b: str) -> pd.DataFrame:
    return run(
        "select m.format, m.year, m.match_date, w.team_name as winner, m.margin_type, m.margin_value, m.stage "
        "from gold.fact_matches m left join gold.dim_teams w on w.team_id = m.winner_id "
        "where (m.team1_id = ? and m.team2_id = ?) or (m.team1_id = ? and m.team2_id = ?) order by m.match_date",
        (a, b, b, a),
    )


def team_scoring(team_id: str) -> pd.DataFrame:
    return run(
        "select t.format || ' ' || t.year as tournament, t.year, t.format, p.avg_runs_scored, p.avg_runs_conceded, p.avg_run_rate, "
        "p.wins_batting_first, p.wins_chasing from gold.mart_team_performance p "
        "join gold.dim_tournaments t using (tournament_id) where p.team_id = ? order by t.year, t.format",
        (team_id,),
    )


def team_summary(team_id: str) -> pd.DataFrame:
    return run(
        "select p.format, sum(p.matches) as matches, sum(p.wins) as wins, round(100.0 * sum(p.wins) / sum(p.matches), 1) as win_pct, "
        "round(avg(p.avg_runs_scored), 1) as avg_runs_scored, round(avg(p.avg_runs_conceded), 1) as avg_runs_conceded, "
        "count(*) as editions, sum(case when p.is_champion then 1 else 0 end) as titles "
        "from gold.mart_team_performance p where p.team_id = ? group by p.format order by p.format",
        (team_id,),
    )


# ------------------------------------------------------------------ ball by ball
def wicket_progression(mid: str) -> pd.DataFrame:
    return run(
        "select innings_number as innings, over_number as over, "
        "sum(count(*) filter (where is_wicket)) over (partition by innings_number order by over_number) as wickets "
        "from gold.fact_deliveries where match_id = ? and not is_super_over group by innings_number, over_number order by 1, 2",
        (mid,),
    )


def phase_summary(mid: str) -> pd.DataFrame:
    return run(
        "select innings_number as innings, phase, sum(total_runs) as runs, count(*) filter (where is_legal_ball) as legal_balls, "
        "round(6.0 * sum(total_runs) / nullif(count(*) filter (where is_legal_ball), 0), 2) as run_rate, "
        "count(*) filter (where is_wicket) as wickets, round(100.0 * count(*) filter (where is_dot_ball) / count(*), 1) as dot_pct, "
        "count(*) filter (where is_boundary) as boundaries from gold.fact_deliveries "
        "where match_id = ? and not is_super_over group by 1, 2 order by 1, min(delivery_sequence)",
        (mid,),
    )


def first_innings_balls(mid: str) -> pd.DataFrame:
    return run(
        "select match_id, format, over_number, total_runs, is_wicket, is_legal_ball, is_boundary, is_dot_ball "
        "from gold.fact_deliveries where match_id = ? and innings_number = 1 and not is_super_over order by delivery_sequence",
        (mid,),
    )


# ------------------------------------------------------------------ data engineering
def inventory() -> pd.DataFrame:
    tables = [
        "dim_dates",
        "dim_teams",
        "dim_players",
        "dim_venues",
        "dim_tournaments",
        "fact_matches",
        "fact_innings",
        "fact_deliveries",
        "fact_player_performances",
        "fact_super_over_performances",
        "fact_tournament_standings",
        "mart_batting",
        "mart_batting_career",
        "mart_bowling",
        "mart_bowling_career",
        "mart_team_performance",
        "mart_tournament_summary",
        "mart_data_coverage",
    ]
    rows = []
    for t in tables:
        n = int(run(f"select count(*) as n from gold.{t}")["n"].iloc[0])
        cols = len(run(f"select * from gold.{t} limit 0").columns)
        rows.append({"layer": "gold", "table": t, "rows": n, "columns": cols})
    return pd.DataFrame(rows)


def null_profile(table: str) -> pd.DataFrame:
    cols = run(f"select * from gold.{table} limit 0").columns.tolist()
    sql = (
        "select "
        + ", ".join(
            f'round(100.0 * count(*) filter (where "{c}" is null) / count(*), 1) as "{c}"'
            for c in cols
        )
        + f" from gold.{table}"
    )
    row = run(sql).iloc[0]
    return pd.DataFrame({"column": cols, "null_pct": [float(row[c]) for c in cols]}).sort_values(
        "null_pct", ascending=False
    )


def bronze_manifest() -> pd.DataFrame:
    path = PROJECT_ROOT / "data" / "bronze" / "_manifest.json"
    if not path.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    return (
        df.sort_values("written_at")
        .groupby("entity", as_index=False)
        .last()[["entity", "batch_id", "rows", "written_at"]]
    )


def file_freshness() -> pd.DataFrame:
    items = {
        "bronze manifest": PROJECT_ROOT / "data" / "bronze" / "_manifest.json",
        "silver (matches)": PROJECT_ROOT / "data" / "silver" / "matches",
        "gold (fact_matches)": PROJECT_ROOT / "data" / "gold" / "fact_matches" / "part-0.parquet",
        "DuckDB warehouse": PROJECT_ROOT / "data" / "warehouse" / "cricket_gold.duckdb",
        "features": FEATURES / "match_features.parquet",
        "models": PROJECT_ROOT / "models" / "winner_logistic.joblib",
        "executive report": REPORTS / "executive_report.md",
    }
    rows = []
    for name, path in items.items():
        if path.exists():
            ts = (
                max(
                    (f.stat().st_mtime for f in path.rglob("*") if f.is_file()),
                    default=path.stat().st_mtime,
                )
                if path.is_dir()
                else path.stat().st_mtime
            )
            rows.append(
                {
                    "artifact": name,
                    "last_updated": pd.Timestamp(ts, unit="s").strftime("%Y-%m-%d %H:%M"),
                }
            )
        else:
            rows.append({"artifact": name, "last_updated": "missing"})
    return pd.DataFrame(rows)


def projection_crossover(fmt: str) -> tuple[int | None, str]:
    """First checkpoint over from which run-rate extrapolation is at least as good as the model.

    Returns (over, sentence). Computed from the held-out evaluation, never typed."""
    m = report_csv("model_evaluation/innings_projection_metrics.csv")
    if m is None:
        return None, ""
    d = m[
        (m["format"] == fmt)
        & m["scope"].str.startswith("over")
        & m["model"].isin(["baseline_run_rate", "linear_regression"])
    ].copy()
    d["over"] = d["scope"].str.replace("over ", "").astype(int)
    p = d.pivot(index="over", columns="model", values="mae").sort_index()
    worse = p[p["baseline_run_rate"] <= p["linear_regression"]]
    if worse.empty:
        return None, f"{fmt}: the model beats run-rate extrapolation at every evaluated checkpoint."
    over = int(worse.index.min())
    return over, (
        f"{fmt}: the model is more accurate than run-rate extrapolation up to about over {over - 1}; from over {over} on, plain extrapolation is at least as accurate on held-out tournaments."
    )
