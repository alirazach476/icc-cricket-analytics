-- Bowling by phase: player x format x phase. Runs conceded exclude byes and leg-byes; wickets exclude
-- run-outs and retirements (not credited to the bowler). Super Overs excluded.
with d as (
    select * from {{ source('gold', 'fact_deliveries') }}
    where not is_super_over and phase in ('powerplay', 'middle', 'death')
)
select
    md5(bowler_id || '|' || format || '|' || phase)                 as phase_bowling_key,
    bowler_id                                                       as player_id,
    format,
    phase,
    count(distinct match_id)                                        as matches,
    count(*) filter (where is_legal_ball)                           as legal_balls,
    sum(batter_runs + case when is_wide or is_no_ball then extra_runs else 0 end) as runs_conceded,
    count(*) filter (where is_wicket
        and dismissal_type not in ('run out', 'retired out', 'retired hurt', 'obstructing the field')) as wickets,
    count(*) filter (where is_dot_ball and is_legal_ball)           as dot_balls,
    round(6.0 * sum(batter_runs + case when is_wide or is_no_ball then extra_runs else 0 end)
          / nullif(count(*) filter (where is_legal_ball), 0), 2)    as economy,
    round(100.0 * count(*) filter (where is_dot_ball and is_legal_ball)
          / nullif(count(*) filter (where is_legal_ball), 0), 2)    as dot_ball_pct
from d
group by bowler_id, format, phase
