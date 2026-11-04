"""Tournament-level analytics and coverage snapshots (Stage 13)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analytics.duckdb_client import read_sql


def tournament_coverage(*, tournament_id: str | None = None) -> pd.DataFrame:
    if tournament_id:
        sql = """
            select *
            from analytics_marts.mart_tournament_summary
            where tournament_id = ?
        """
        return read_sql(sql, tournament_id=tournament_id, params=[tournament_id])
    sql = "select * from analytics_marts.mart_tournament_summary order by tournament_year, tournament_format"
    return read_sql(sql, tournament_id=tournament_id)


def match_results(*, tournament_id: str) -> pd.DataFrame:
    sql = """
        select
            match_id,
            match_number,
            match_stage,
            match_date,
            team1_name,
            team2_name,
            toss_winner_name,
            toss_decision,
            winner_name,
            result_margin,
            scorecard_status,
            ball_by_ball_status
        from analytics_marts.dim_matches
        where tournament_id = ?
        order by match_date nulls last, match_number nulls last, match_id
    """
    return read_sql(sql, tournament_id=tournament_id, params=[tournament_id])


def tournament_summary(*, tournament_id: str) -> dict[str, Any]:
    cov = tournament_coverage(tournament_id=tournament_id)
    results = match_results(tournament_id=tournament_id)
    coverage_row = cov.to_dict(orient="records")[0] if len(cov) else None
    return {
        "tournament_id": tournament_id,
        "coverage": coverage_row,
        "match_count": int(len(results)),
        "matches": results.to_dict(orient="records"),
        "claims_complete_coverage": False,
        "notes": "Coverage counts reflect loaded warehouse/dbt rows only.",
    }
