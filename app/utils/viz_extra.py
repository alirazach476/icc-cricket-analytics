# ruff: noqa: E501
"""Aggregated data for the extra batting, bowling, team, matchup and stage charts (all computed in the database)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.utils.database import run

STAGE_ORDER = [
    "First Round",
    "Group Stage",
    "Super Six",
    "Super Eight",
    "Super Ten",
    "Super 12",
    "Quarterfinal",
    "Semifinal",
    "Final",
]
STAGE_GROUP = {
    "First Round": "Group stage",
    "Group Stage": "Group stage",
    "Super Six": "Second stage",
    "Super Eight": "Second stage",
    "Super Ten": "Second stage",
    "Super 12": "Second stage",
    "Quarterfinal": "Knockout",
    "Semifinal": "Knockout",
    "Final": "Knockout",
}
GROUP_ORDER = ["Group stage", "Second stage", "Knockout"]
NOT_BOWLER = "('run out','retired hurt','retired out','obstructing the field')"


def batting_leaders(tid: str) -> pd.DataFrame:
    return run(
        "select p.full_name as player, t.team_name as team, b.innings, b.runs, b.balls_faced, b.fours, b.sixes, b.fifties, b.hundreds, "
        "b.average, b.strike_rate from gold.mart_batting b join gold.dim_players p using (player_id) "
        "join gold.dim_teams t on t.team_id = b.team_id where b.tournament_id = ?",
        (tid,),
    )


def batting_by_edition(fmt: str, n: int = 8) -> pd.DataFrame:
    """The n highest career run scorers of a format, with runs / average / strike rate in every edition they played."""
    return run(
        "with top as (select player_id from gold.mart_batting_career where format = ? order by runs desc limit ?) "
        "select p.full_name as player, b.year, b.runs, b.average, b.strike_rate, b.innings from gold.mart_batting b "
        "join top using (player_id) join gold.dim_players p using (player_id) where b.format = ? order by b.year",
        (fmt, n, fmt),
    )


def bowling_leaders(tid: str) -> pd.DataFrame:
    return run(
        "select p.full_name as player, t.team_name as team, w.matches, w.balls_bowled, w.overs, w.maidens, w.runs_conceded, "
        "w.wickets, w.dots, w.economy, w.average, w.strike_rate from gold.mart_bowling w join gold.dim_players p using (player_id) "
        "join gold.dim_teams t on t.team_id = w.team_id where w.tournament_id = ?",
        (tid,),
    )


def bowling_by_edition(fmt: str, min_balls: int = 60) -> pd.DataFrame:
    return run(
        "select p.full_name as player, w.year, w.balls_bowled, w.wickets, w.economy, w.average, w.strike_rate "
        "from gold.mart_bowling w join gold.dim_players p using (player_id) where w.format = ? and w.balls_bowled >= ? order by w.year",
        (fmt, int(min_balls)),
    )


def bowling_economy_matrix(fmt: str, n: int = 12, min_balls: int = 30) -> pd.DataFrame:
    """Economy of the n leading wicket-takers of a format in every edition where they bowled enough."""
    return run(
        "with top as (select player_id from gold.mart_bowling_career where format = ? order by wickets desc limit ?) "
        "select p.full_name as player, w.year, w.economy, w.balls_bowled from gold.mart_bowling w join top using (player_id) "
        "join gold.dim_players p using (player_id) where w.format = ? and w.balls_bowled >= ?",
        (fmt, n, fmt, int(min_balls)),
    )


def team_stage_record(team_id: str) -> pd.DataFrame:
    """Wins, losses and no-results of one team by match stage and format."""
    d = run(
        "select format, stage, "
        "count(*) filter (where winner_id = ?) as wins, "
        "count(*) filter (where winner_id is not null and winner_id <> ?) as losses, "
        "count(*) filter (where winner_id is null and is_completed) as no_winner, count(*) as matches "
        "from gold.fact_matches where ? in (team1_id, team2_id) and is_completed group by 1, 2",
        (team_id, team_id, team_id),
    )
    d["stage"] = pd.Categorical(d["stage"], [s for s in STAGE_ORDER if s in set(d["stage"])], ordered=True)
    return d.sort_values(["format", "stage"]).reset_index(drop=True)


def team_trend(team_id: str) -> pd.DataFrame:
    return run(
        "select format, year, matches, wins, win_pct, avg_runs_scored, avg_runs_conceded, highest_total, lowest_total, avg_run_rate "
        "from gold.mart_team_performance where team_id = ? order by year",
        (team_id,),
    )


def matchups(tid: str, min_balls: int = 12) -> pd.DataFrame:
    """Batter v bowler records in one tournament; pairs with fewer than ``min_balls`` balls are left out (too noisy)."""
    return run(
        "select bt.full_name as batter, bw.full_name as bowler, count(*) filter (where not d.is_wide) as balls, sum(d.batter_runs) as runs, "
        f"count(*) filter (where d.is_wicket and d.dismissed_player_id = d.batter_id and coalesce(d.dismissal_type, '') not in {NOT_BOWLER}) as dismissals, "
        "count(*) filter (where d.is_dot_ball) as dots, count(*) filter (where d.is_four) as fours, count(*) filter (where d.is_six) as sixes "
        "from gold.fact_deliveries d join gold.dim_players bt on bt.player_id = d.batter_id join gold.dim_players bw on bw.player_id = d.bowler_id "
        "where d.tournament_id = ? and not d.is_super_over group by 1, 2 having count(*) filter (where not d.is_wide) >= ? order by balls desc",
        (tid, int(min_balls)),
    )


def stage_comparison(fmt: str) -> pd.DataFrame:
    """First-innings totals and bat-first results by stage group (group / second stage / knockout) for one format."""
    d = run(
        "select m.stage, i.total_runs, (m.winner_id = m.batting_first_team_id) as bat_first_won, (m.winner_id is not null) as decided "
        "from gold.fact_innings i join gold.fact_matches m using (match_id) "
        "where m.format = ? and i.innings_number = 1 and not i.is_super_over and i.total_runs is not null and m.is_completed and not m.is_dls",
        (fmt,),
    )
    d["group"] = d["stage"].map(STAGE_GROUP).fillna("Other")
    return d


def mean_ci(x: pd.Series, z: float = 1.96) -> tuple[float, float, float, int]:
    n = int(x.notna().sum())
    if n < 2:
        return (float(x.mean()) if n else np.nan, np.nan, np.nan, n)
    m, se = float(x.mean()), float(x.std(ddof=1) / np.sqrt(n))
    return m, m - z * se, m + z * se, n


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return np.nan, np.nan, np.nan
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def tournament_id_of(match_id: str) -> str | None:
    d = run("select tournament_id from gold.fact_matches where match_id = ?", (match_id,))
    return None if d.empty else d.iloc[0, 0]
