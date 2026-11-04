"""Batting analytics from dbt marts (Stage 13). Aggregates loaded rows only."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analytics.duckdb_client import read_sql


def top_run_scorers(
    *,
    tournament_id: str,
    limit: int = 20,
) -> pd.DataFrame:
    """Top run-scorers from loaded batting scorecards for a tournament."""
    sql = """
        select
            tournament_id,
            player_id,
            player_name,
            innings_batted,
            runs,
            balls_faced,
            fours,
            sixes,
            high_score,
            case
                when balls_faced > 0 then round(100.0 * runs / balls_faced, 2)
                else null
            end as strike_rate
        from analytics_marts.mart_batting_tournament_totals
        where tournament_id = ?
        order by runs desc, high_score desc
        limit ?
    """
    return read_sql(sql, tournament_id=tournament_id, params=[tournament_id, limit])


def batting_leaderboard_summary(*, tournament_id: str, limit: int = 10) -> dict[str, Any]:
    df = top_run_scorers(tournament_id=tournament_id, limit=limit)
    return {
        "tournament_id": tournament_id,
        "metric": "runs",
        "source": "analytics_marts.mart_batting_tournament_totals",
        "row_count": int(len(df)),
        "leaders": df.to_dict(orient="records"),
        "notes": "Derived only from loaded scorecard rows; not a claim of complete coverage.",
    }


def most_boundaries(*, tournament_id: str, limit: int = 10) -> pd.DataFrame:
    sql = """
        select
            tournament_id,
            player_id,
            player_name,
            fours,
            sixes,
            (fours + sixes) as boundaries,
            runs
        from analytics_marts.mart_batting_tournament_totals
        where tournament_id = ?
        order by boundaries desc, sixes desc, runs desc
        limit ?
    """
    return read_sql(sql, tournament_id=tournament_id, params=[tournament_id, limit])
