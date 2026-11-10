# ruff: noqa: E501
"""Queries behind the dashboard visuals (all read-only, parameterised, cached via ``run``)."""

from __future__ import annotations

import pandas as pd

from app.utils.analytics import feature_parquet
from app.utils.database import competition as database_competition
from app.utils.database import run


# ------------------------------------------------------------------ home / global
def hosts() -> pd.DataFrame:
    return run(
        "select tournament_id, tournament_name, format, year, host_country from gold.dim_tournaments order by format, year"
    )


def team_match_counts() -> pd.DataFrame:
    return run(
        "select t.team_name as team, m.format, count(*) as matches from gold.fact_matches m "
        "join gold.dim_teams t on t.team_id in (m.team1_id, m.team2_id) group by 1, 2 order by 3 desc"
    )


def stage_sunburst() -> pd.DataFrame:
    return run(
        "select format, cast(year as varchar) as year, coalesce(stage, 'Unknown') as stage, count(*) as matches from gold.fact_matches group by 1, 2, 3"
    )


def toss_flow() -> pd.DataFrame:
    return run(
        "select toss_decision, case when winner_id = toss_winner_id then 'toss winner won' else 'toss winner lost' end as outcome, count(*) as matches "
        "from gold.fact_matches where toss_decision is not null and winner_id is not null and toss_winner_id is not null group by 1, 2"
    )


def match_dates() -> pd.Series:
    return run("select match_date from gold.fact_matches")["match_date"]


def top_batters_all(fmt: str, n: int = 10) -> pd.DataFrame:
    return run(
        "select p.full_name as player, b.runs, b.average, b.strike_rate, b.hundreds from gold.mart_batting_career b "
        "join gold.dim_players p using (player_id) where b.format = ? order by b.runs desc limit ?",
        (fmt, n),
    )


def top_bowlers_all(fmt: str, n: int = 10) -> pd.DataFrame:
    return run(
        "select p.full_name as player, b.wickets, b.economy, b.average, b.best_figures from gold.mart_bowling_career b "
        "join gold.dim_players p using (player_id) where b.format = ? order by b.wickets desc, b.economy limit ?",
        (fmt, n),
    )


def edition_stats() -> pd.DataFrame:
    return run(
        "select tournament_name, format, year, matches, runs_per_match, avg_first_innings_score, "
        "fours * 1.0 / matches as fours_per_match, sixes * 1.0 / matches as sixes_per_match, total_wickets * 1.0 / matches as wickets_per_match, "
        "bat_first_win_pct, ties, dls_matches from gold.mart_tournament_summary order by format, year"
    )


# ------------------------------------------------------------------ tournament
def tournament_innings(tid: str) -> pd.DataFrame:
    return run(
        "select i.match_id, i.match_date, i.stage, i.innings_number, i.batting_team, i.bowling_team, i.total_runs, i.wickets, i.overs, i.run_rate, "
        "i.fours, i.sixes, i.extras, i.is_chase, i.target, v.venue_name as venue from gold.fact_innings i "
        "join gold.fact_matches m on m.match_id = i.match_id left join gold.dim_venues v on v.venue_id = m.venue_id "
        "where i.tournament_id = ? and not i.is_super_over order by i.match_date",
        (tid,),
    )


def tournament_venues(tid: str) -> pd.DataFrame:
    return run(
        "select v.venue_name, v.city, count(*) as matches, round(avg(m.first_innings_runs), 1) as avg_first_innings "
        "from gold.fact_matches m join gold.dim_venues v using (venue_id) where m.tournament_id = ? group by 1, 2 order by 3 desc",
        (tid,),
    )


def tournament_dismissals(tid: str) -> pd.DataFrame:
    return run(
        "select dismissal_type, count(*) as wickets from gold.fact_deliveries where tournament_id = ? and is_wicket and not is_super_over group by 1 order by 2 desc",
        (tid,),
    )


def batter_bubble(tid: str) -> pd.DataFrame:
    return run(
        "select p.full_name as player, t.team_name as team, b.runs, b.innings, b.average, b.strike_rate, b.hundreds + b.fifties as milestones "
        "from gold.mart_batting b join gold.dim_players p using (player_id) join gold.dim_teams t on t.team_id = b.team_id "
        "where b.tournament_id = ? and b.balls_faced >= 30",
        (tid,),
    )


def bowler_bubble(tid: str) -> pd.DataFrame:
    return run(
        "select p.full_name as player, t.team_name as team, b.wickets, b.economy, b.matches, b.average from gold.mart_bowling b "
        "join gold.dim_players p using (player_id) join gold.dim_teams t on t.team_id = b.team_id where b.tournament_id = ? and b.balls_bowled >= 24",
        (tid,),
    )


def match_scores(tid: str | None = None) -> pd.DataFrame:
    where = "where tournament_id = ? and" if tid else "where"
    params = (tid,) if tid else ()
    return run(
        f"select match_id, match_date, format, year, stage, first_innings_runs as first_innings, second_innings_runs as second_innings, "
        f"winner_id = batting_first_team_id as bat_first_won, winner_name, team1_name, team2_name from gold.fact_matches "
        f"{where} is_completed and not is_walkover and first_innings_runs is not null and second_innings_runs is not null",
        params,
    )


# ------------------------------------------------------------------ squads
def squads_all() -> pd.DataFrame:
    return run(
        "select s.tournament_id, d.tournament_name, d.format, d.year, s.team_id, t.team_name, s.player_id, s.full_name, s.role_code, s.playing_role, "
        "s.is_captain, s.is_wicketkeeper, s.batting_style, s.bowling_style, s.age_at_tournament, s.is_overseas, s.is_withdrawn, s.played_for_team, "
        "s.matches_played, s.source from gold.fact_squads s join gold.dim_tournaments d using (tournament_id) join gold.dim_teams t using (team_id)"
    )


def player_squad_history(pid: str) -> pd.DataFrame:
    return run(
        "select d.format || ' ' || d.year as tournament, d.format, d.year, t.team_name as team, s.playing_role as role, s.is_captain as captain, "
        "s.matches_played, s.age_at_tournament as age from gold.fact_squads s join gold.dim_tournaments d using (tournament_id) "
        "join gold.dim_teams t using (team_id) where s.player_id = ? order by d.year, d.format",
        (pid,),
    )


def player_info(pid: str) -> pd.Series | None:
    d = run(
        "select p.full_name, p.batting_style, p.bowling_style, p.date_of_birth, "
        "(select string_agg(distinct t.team_name, ', ') from gold.fact_squads s join gold.dim_teams t using (team_id) where s.player_id = p.player_id) as teams, "
        "(select any_value(s.playing_role) from gold.fact_squads s join gold.dim_tournaments d using (tournament_id) where s.player_id = p.player_id) as role "
        "from gold.dim_players p where p.player_id = ?",
        (pid,),
    )
    return None if d.empty else d.iloc[0]


# ------------------------------------------------------------------ player
def player_innings_full(pid: str) -> pd.DataFrame:
    return run(
        "select f.match_id, f.match_date, f.year, f.format, f.stage, f.runs, f.balls_faced, f.fours, f.sixes, f.batting_position as pos, f.is_out, f.dismissal_type, "
        "o.team_name as opposition, d.format || ' ' || d.year as tournament, f.team_won "
        "from gold.fact_player_performances f join gold.dim_teams o on o.team_id = f.opposition_team_id join gold.dim_tournaments d using (tournament_id) "
        "where f.player_id = ? and f.did_bat and f.runs is not null order by f.match_date",
        (pid,),
    )


def player_bowling_full(pid: str) -> pd.DataFrame:
    return run(
        "select f.match_id, f.match_date, f.year, f.format, f.wickets, f.runs_conceded, f.overs_bowled, f.economy, f.maidens, f.dots, o.team_name as opposition, d.format || ' ' || d.year as tournament "
        "from gold.fact_player_performances f join gold.dim_teams o on o.team_id = f.opposition_team_id join gold.dim_tournaments d using (tournament_id) "
        "where f.player_id = ? and f.did_bowl order by f.match_date",
        (pid,),
    )


def player_dismissed_by_type(pid: str) -> pd.DataFrame:
    return run(
        "select dismissal_type, count(*) as n from gold.fact_deliveries where dismissed_player_id = ? and is_wicket and not is_super_over group by 1 order by 2 desc",
        (pid,),
    )


def player_wickets_by_type(pid: str) -> pd.DataFrame:
    return run(
        "select dismissal_type, count(*) as n from gold.fact_deliveries where bowler_id = ? and is_wicket and not is_super_over "
        "and dismissal_type not in ('run out', 'retired out', 'retired hurt', 'obstructing the field') group by 1 order by 2 desc",
        (pid,),
    )


def player_bowling_phases(pid: str) -> pd.DataFrame:
    return run(
        "select format, phase, count(*) filter (where is_legal_ball) as balls, round(6.0 * sum(batter_runs + case when is_wide or is_no_ball then extra_runs else 0 end) / nullif(count(*) filter (where is_legal_ball), 0), 2) as economy, "
        "count(*) filter (where is_wicket and dismissal_type not in ('run out','retired out','retired hurt','obstructing the field')) as wickets "
        "from gold.fact_deliveries where bowler_id = ? and not is_super_over and phase in ('powerplay','middle','death') group by 1, 2",
        (pid,),
    )


def batting_percentiles(pid: str, fmt: str, min_balls: int = 300, min_runs: int = 0) -> dict[str, float] | None:
    d = run(
        "select * from (select player_id, percent_rank() over (order by runs) as runs, percent_rank() over (order by average) as average, "
        "percent_rank() over (order by strike_rate) as strike_rate, percent_rank() over (order by sixes * 1.0 / innings) as sixes, "
        "percent_rank() over (order by (hundreds + fifties) * 1.0 / innings) as milestones from gold.mart_batting_career where format = ? and balls_faced >= ? and runs >= ?) where player_id = ?",
        (fmt, int(min_balls), int(min_runs), pid),
    )
    return (
        None
        if d.empty
        else {
            k: float(100 * d.iloc[0][k])
            for k in ("runs", "average", "strike_rate", "sixes", "milestones")
        }
    )


def bowling_percentiles(pid: str, fmt: str, min_balls: int = 300) -> dict[str, float] | None:
    d = run(
        "select * from (select player_id, percent_rank() over (order by wickets) as wickets, percent_rank() over (order by -economy) as economy, "
        "percent_rank() over (order by -average) as average, percent_rank() over (order by -strike_rate) as strike_rate, "
        "percent_rank() over (order by five_wicket_hauls + four_wicket_hauls) as hauls from gold.mart_bowling_career where format = ? and balls_bowled >= ?) where player_id = ?",
        (fmt, int(min_balls), pid),
    )
    return (
        None
        if d.empty
        else {
            k: float(100 * d.iloc[0][k])
            for k in ("wickets", "economy", "average", "strike_rate", "hauls")
        }
    )


# ------------------------------------------------------------------ team
def team_vs_opponents(team_id: str) -> pd.DataFrame:
    return run(
        "select o.team_name as opponent, count(*) as matches, count(*) filter (where m.winner_id = ?) as wins, "
        "round(100.0 * count(*) filter (where m.winner_id = ?) / nullif(count(*) filter (where m.winner_id is not null), 0), 1) as win_pct "
        "from gold.fact_matches m join gold.dim_teams o on o.team_id = case when m.team1_id = ? then m.team2_id else m.team1_id end "
        "where ? in (m.team1_id, m.team2_id) and m.is_completed group by 1 having count(*) filter (where m.winner_id is not null) >= 1 order by matches desc",
        (team_id, team_id, team_id, team_id),
    )


def team_top_batters(team_id: str, n: int = 10) -> pd.DataFrame:
    return run(
        "select p.full_name as player, sum(f.runs) as runs, count(*) filter (where f.did_bat) as innings, round(sum(f.runs) * 1.0 / nullif(count(*) filter (where f.is_out), 0), 1) as average "
        "from gold.fact_player_performances f join gold.dim_players p using (player_id) where f.team_id = ? and f.did_bat group by 1 order by 2 desc limit ?",
        (team_id, n),
    )


def team_top_bowlers(team_id: str, n: int = 10) -> pd.DataFrame:
    return run(
        "select p.full_name as player, sum(f.wickets) as wickets, round(6.0 * sum(f.runs_conceded) / nullif(sum(f.balls_bowled), 0), 2) as economy "
        "from gold.fact_player_performances f join gold.dim_players p using (player_id) where f.team_id = ? and f.did_bowl group by 1 order by 2 desc limit ?",
        (team_id, n),
    )


def team_venues(team_id: str) -> pd.DataFrame:
    return run(
        "select v.venue_name, count(*) as matches, count(*) filter (where m.winner_id = ?) as wins from gold.fact_matches m join gold.dim_venues v using (venue_id) "
        "where ? in (m.team1_id, m.team2_id) group by 1 order by 2 desc limit 12",
        (team_id, team_id),
    )


def team_toss(team_id: str) -> pd.DataFrame:
    return run(
        "select toss_decision, case when winner_id = ? then 'won match' else 'did not win' end as result, count(*) as n from gold.fact_matches "
        "where toss_winner_id = ? and toss_decision is not null group by 1, 2",
        (team_id, team_id),
    )


def team_summary_all() -> pd.DataFrame:
    return run(
        "select t.team_name as team, p.format, sum(p.matches) as matches, sum(p.wins) as wins, round(100.0 * sum(p.wins) / sum(p.matches), 1) as win_pct, "
        "round(avg(p.avg_runs_scored), 1) as runs_scored, round(avg(p.avg_runs_conceded), 1) as runs_conceded, sum(p.wins_batting_first) as wins_bat_first, "
        "sum(p.wins_chasing) as wins_chasing, sum(case when p.is_champion then 1 else 0 end) as titles, count(*) as editions "
        "from gold.mart_team_performance p join gold.dim_teams t using (team_id) group by 1, 2"
    )


def team_year_matrix(fmt: str) -> pd.DataFrame:
    return run(
        "select t.team_name as team, d.year, p.win_pct from gold.mart_team_performance p join gold.dim_teams t using (team_id) "
        "join gold.dim_tournaments d using (tournament_id) where p.format = ?",
        (fmt,),
    )


def elo_history(fmt: str) -> pd.DataFrame:
    # World Cups: match_features.parquet; Champions Trophy / Test Championship: <code>_match_features.parquet
    code = database_competition()
    f = feature_parquet("match_features.parquet" if code == "wc" else f"{code}_match_features.parquet")
    if f is None:
        return pd.DataFrame()
    f = f[f["format"] == fmt]
    a = f[["match_date", "team_a_id", "elo_a"]].rename(
        columns={"team_a_id": "team_id", "elo_a": "elo"}
    )
    b = f[["match_date", "team_b_id", "elo_b"]].rename(
        columns={"team_b_id": "team_id", "elo_b": "elo"}
    )
    out = pd.concat([a, b]).sort_values("match_date")
    teams = run("select team_id, team_name as team from gold.dim_teams")
    return out.merge(teams, on="team_id")


# ------------------------------------------------------------------ matches
def venue_bubble(min_matches: int = 6) -> pd.DataFrame:
    return run(
        "select v.venue_name, v.city, m.format, count(*) as matches, round(avg(m.first_innings_runs), 1) as avg_first_innings, "
        "round(100.0 * count(*) filter (where m.winner_id = m.batting_first_team_id) / nullif(count(*) filter (where m.winner_id is not null), 0), 1) as bat_first_win_pct "
        "from gold.fact_matches m join gold.dim_venues v using (venue_id) where m.is_completed and not m.is_walkover and not m.is_dls group by 1, 2, 3 having count(*) >= ?",
        (min_matches,),
    )


def innings_totals() -> pd.DataFrame:
    return run(
        "select format, stage, total_runs, wickets, is_chase, year from gold.fact_innings where not is_super_over and total_runs is not null"
    )


def margins_by_stage() -> pd.DataFrame:
    return run(
        "select format, coalesce(stage, 'Unknown') as stage, margin_type, margin_value from gold.fact_matches where margin_type in ('runs', 'wickets')"
    )


# ------------------------------------------------------------------ ball by ball
def bbb(mid: str) -> pd.DataFrame:
    return run(
        "select d.innings_number as innings, d.over_number as over, d.ball_number as ball, d.legal_delivery_number as legal_ball, d.phase, "
        "b.full_name as batter, w.full_name as bowler, d.batter_runs, d.extra_runs, d.total_runs, d.is_wicket, d.dismissal_type, "
        "d.is_four, d.is_six, d.is_dot_ball, d.is_wide, d.is_no_ball, d.is_legal_ball, d.extras_type, d.cumulative_runs, d.cumulative_wickets, "
        "bt.team_name as batting_team, d.delivery_sequence from gold.fact_deliveries d "
        "join gold.dim_players b on b.player_id = d.batter_id join gold.dim_players w on w.player_id = d.bowler_id "
        "join gold.dim_teams bt on bt.team_id = d.batting_team_id where d.match_id = ? and not d.is_super_over order by d.innings_number, d.delivery_sequence",
        (mid,),
    )


def innings_targets(mid: str) -> pd.DataFrame:
    return run(
        "select innings_number as innings, target, total_runs, overs from gold.fact_innings where match_id = ? and not is_super_over order by 1",
        (mid,),
    )
