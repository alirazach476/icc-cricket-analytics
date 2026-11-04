"""Bowling analytics from dbt marts (Stage 13). Aggregates loaded rows only."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analytics.duckdb_client import read_sql


def top_wicket_takers(
    *,
    tournament_id: str,
    limit: int = 20,
) -> pd.DataFrame:
    sql = """
        select
            tournament_id,
            player_id,
            player_name,
            innings_bowled,
            wickets,
            runs_conceded,
            maidens,
            wides,
            no_balls,
            case
                when wickets > 0 then round(runs_conceded * 1.0 / wickets, 2)
                else null
            end as bowling_average
        from analytics_marts.mart_bowling_tournament_totals
        where tournament_id = ?
        order by wickets desc, runs_conceded asc
        limit ?
    """
    return read_sql(sql, tournament_id=tournament_id, params=[tournament_id, limit])


def bowling_leaderboard_summary(*, tournament_id: str, limit: int = 10) -> dict[str, Any]:
    df = top_wicket_takers(tournament_id=tournament_id, limit=limit)
    return {
        "tournament_id": tournament_id,
        "metric": "wickets",
        "source": "analytics_marts.mart_bowling_tournament_totals",
        "row_count": int(len(df)),
        "leaders": df.to_dict(orient="records"),
        "notes": "Derived only from loaded scorecard rows; not a claim of complete coverage.",
    }
