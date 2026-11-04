"""Team analytics from dbt marts (Stage 13)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analytics.duckdb_client import read_sql


def team_match_record(*, tournament_id: str) -> pd.DataFrame:
    """Wins / appearances for teams in loaded matches (RESULT winners only counted as wins)."""
    sql = """
        with appearances as (
            select tournament_id, team1_id as team_id, team1_name as team_name, match_id
            from analytics_marts.dim_matches
            where tournament_id = ? and team1_id is not null
            union all
            select tournament_id, team2_id as team_id, team2_name as team_name, match_id
            from analytics_marts.dim_matches
            where tournament_id = ? and team2_id is not null
        ),
        wins as (
            select winner_id as team_id, count(*) as wins
            from analytics_marts.dim_matches
            where tournament_id = ?
              and winner_id is not null
              and coalesce(match_status, result_type) = 'RESULT'
            group by winner_id
        )
        select
            a.tournament_id,
            a.team_id,
            max(a.team_name) as team_name,
            count(distinct a.match_id) as matches_played,
            coalesce(max(w.wins), 0) as wins,
            count(distinct a.match_id) - coalesce(max(w.wins), 0) as non_wins
        from appearances a
        left join wins w on w.team_id = a.team_id
        group by a.tournament_id, a.team_id
        order by wins desc, matches_played desc, team_name
    """
    return read_sql(
        sql,
        tournament_id=tournament_id,
        params=[tournament_id, tournament_id, tournament_id],
    )


def team_innings_totals(*, tournament_id: str) -> pd.DataFrame:
    sql = """
        select
            tournament_id,
            batting_team_id as team_id,
            max(batting_team_name) as team_name,
            count(*) as innings_count,
            round(avg(total_runs), 2) as avg_total_runs,
            max(total_runs) as highest_total,
            min(total_runs) as lowest_total
        from analytics_marts.fct_innings
        where tournament_id = ?
          and coalesce(is_super_over, false) = false
        group by tournament_id, batting_team_id
        order by avg_total_runs desc
    """
    return read_sql(sql, tournament_id=tournament_id, params=[tournament_id])


def team_analytics_summary(*, tournament_id: str) -> dict[str, Any]:
    record = team_match_record(tournament_id=tournament_id)
    totals = team_innings_totals(tournament_id=tournament_id)
    return {
        "tournament_id": tournament_id,
        "match_records": record.to_dict(orient="records"),
        "innings_totals": totals.to_dict(orient="records"),
        "notes": "non_wins includes losses, NR, ties, and matches without a RESULT winner — not fabricated.",
    }
