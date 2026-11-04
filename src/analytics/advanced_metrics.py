"""Advanced metrics from loaded scorecards / BBB (Stage 13).

Never invents missing balls or player careers. Metrics that require complete BBB
are skipped (with an explicit note) when ball-by-ball coverage is incomplete.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analytics.duckdb_client import read_sql
from src.analytics.tournament_analytics import tournament_coverage


def batting_phase_rates_from_bbb(*, tournament_id: str) -> dict[str, Any]:
    """Dot / boundary rates from complete-BBB matches only."""
    cov = tournament_coverage(tournament_id=tournament_id)
    if cov.empty:
        return {"tournament_id": tournament_id, "status": "no_coverage_row", "rows": []}

    complete = int(cov.iloc[0].get("matches_bbb_complete") or 0)
    if complete == 0:
        return {
            "tournament_id": tournament_id,
            "status": "bbb_unavailable",
            "rows": [],
            "notes": "No matches with ball_by_ball_status=complete; phase rates not computed.",
        }

    sql = """
        with complete_matches as (
            select match_id
            from analytics_marts.dim_matches
            where tournament_id = ?
              and ball_by_ball_status = 'complete'
        )
        select
            d.batter_id as player_id,
            p.full_name as player_name,
            count(*) as balls_faced_legalish,
            sum(case when d.total_runs = 0 and not d.is_wide then 1 else 0 end) as dots,
            sum(case when d.batter_runs >= 4 then 1 else 0 end) as boundaries,
            sum(d.batter_runs) as batter_runs,
            round(
                100.0 * sum(case when d.total_runs = 0 and not d.is_wide then 1 else 0 end)
                / nullif(count(*), 0),
                2
            ) as dot_ball_pct,
            round(
                100.0 * sum(case when d.batter_runs >= 4 then 1 else 0 end)
                / nullif(count(*), 0),
                2
            ) as boundary_pct
        from analytics_marts.fct_deliveries d
        inner join complete_matches cm on cm.match_id = d.match_id
        left join analytics_marts.dim_players p on p.player_id = d.batter_id
        where d.tournament_id = ?
          and d.batter_id is not null
          and not coalesce(d.is_wide, false)
        group by d.batter_id, p.full_name
        having count(*) >= 30
        order by batter_runs desc
        limit 25
    """
    df = read_sql(sql, tournament_id=tournament_id, params=[tournament_id, tournament_id])
    return {
        "tournament_id": tournament_id,
        "status": "ok",
        "matches_bbb_complete": complete,
        "min_balls": 30,
        "rows": df.to_dict(orient="records"),
        "notes": "Computed only on matches with complete BBB; player_id may be Cricsheet-scoped.",
    }


def bowling_economy_from_bbb(*, tournament_id: str) -> dict[str, Any]:
    cov = tournament_coverage(tournament_id=tournament_id)
    if cov.empty or int(cov.iloc[0].get("matches_bbb_complete") or 0) == 0:
        return {
            "tournament_id": tournament_id,
            "status": "bbb_unavailable",
            "rows": [],
            "notes": "Economy-from-BBB requires complete ball-by-ball matches.",
        }

    sql = """
        with complete_matches as (
            select match_id
            from analytics_marts.dim_matches
            where tournament_id = ?
              and ball_by_ball_status = 'complete'
        ),
        balls as (
            select
                d.bowler_id as player_id,
                p.full_name as player_name,
                sum(case when not coalesce(d.is_wide, false) then 1 else 0 end) as legal_balls,
                sum(d.total_runs) as runs_conceded,
                sum(case when d.is_wicket then 1 else 0 end) as wickets
            from analytics_marts.fct_deliveries d
            inner join complete_matches cm on cm.match_id = d.match_id
            left join analytics_marts.dim_players p on p.player_id = d.bowler_id
            where d.tournament_id = ?
              and d.bowler_id is not null
            group by d.bowler_id, p.full_name
        )
        select
            player_id,
            player_name,
            legal_balls,
            runs_conceded,
            wickets,
            round(legal_balls / 6.0, 2) as overs,
            case
                when legal_balls > 0 then round(runs_conceded * 6.0 / legal_balls, 2)
                else null
            end as economy
        from balls
        where legal_balls >= 60
        order by economy asc nulls last, wickets desc
        limit 25
    """
    df = read_sql(sql, tournament_id=tournament_id, params=[tournament_id, tournament_id])
    return {
        "tournament_id": tournament_id,
        "status": "ok",
        "min_legal_balls": 60,
        "rows": df.to_dict(orient="records"),
        "notes": "Economy from complete-BBB matches only; not merged to ESPN identities by name.",
    }


def venue_averages(*, tournament_id: str) -> pd.DataFrame:
    sql = """
        select
            m.venue,
            m.city,
            count(distinct i.match_id) as matches,
            count(*) as innings,
            round(avg(i.total_runs), 2) as avg_innings_total,
            max(i.total_runs) as highest_total
        from analytics_marts.fct_innings i
        inner join analytics_marts.dim_matches m on m.match_id = i.match_id
        where i.tournament_id = ?
          and coalesce(i.is_super_over, false) = false
          and m.venue is not null
        group by m.venue, m.city
        having count(*) >= 2
        order by avg_innings_total desc
    """
    return read_sql(sql, tournament_id=tournament_id, params=[tournament_id])
