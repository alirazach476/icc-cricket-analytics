-- Observed coverage only — never claims complete historical coverage.
with match_stats as (
    select
        tournament_id,
        max(tournament_name) as tournament_name,
        max(tournament_year) as tournament_year,
        max(tournament_format) as tournament_format,
        count(distinct match_id) as matches_loaded,
        count(distinct case when scorecard_status = 'complete' then match_id end)
            as matches_scorecard_complete,
        count(distinct case when ball_by_ball_status = 'complete' then match_id end)
            as matches_bbb_complete,
        count(distinct case when ball_by_ball_status = 'partial' then match_id end)
            as matches_bbb_partial,
        count(distinct case when ball_by_ball_status = 'unavailable' then match_id end)
            as matches_bbb_unavailable
    from {{ ref('dim_matches') }}
    group by tournament_id
),
innings_stats as (
    select
        tournament_id,
        count(*) as innings_rows
    from {{ ref('fct_innings') }}
    group by tournament_id
),
delivery_stats as (
    select
        tournament_id,
        count(*) as delivery_rows
    from {{ ref('fct_deliveries') }}
    group by tournament_id
)

select
    m.tournament_id,
    m.tournament_name,
    m.tournament_year,
    m.tournament_format,
    m.matches_loaded,
    m.matches_scorecard_complete,
    m.matches_bbb_complete,
    m.matches_bbb_partial,
    m.matches_bbb_unavailable,
    coalesce(i.innings_rows, 0) as innings_rows,
    coalesce(d.delivery_rows, 0) as delivery_rows,
    false as claims_complete_coverage
from match_stats as m
left join innings_stats as i on i.tournament_id = m.tournament_id
left join delivery_stats as d on d.tournament_id = m.tournament_id
