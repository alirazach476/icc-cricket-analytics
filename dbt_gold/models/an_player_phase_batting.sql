-- Batting by phase of the innings: player x format x phase. Ball-by-ball matches only; Super Overs
-- are excluded. Balls faced = every delivery except wides (no-balls are faced).
with d as (
    select * from {{ source('gold', 'fact_deliveries') }}
    where not is_super_over and phase in ('powerplay', 'middle', 'death')
)
select
    md5(batter_id || '|' || format || '|' || phase)                 as phase_batting_key,
    batter_id                                                       as player_id,
    format,
    phase,
    count(distinct match_id)                                        as matches,
    count(*) filter (where not is_wide)                             as balls_faced,
    sum(batter_runs)                                                as runs,
    count(*) filter (where is_dot_ball and not is_wide)             as dot_balls,
    count(*) filter (where is_four)                                 as fours,
    count(*) filter (where is_six)                                  as sixes,
    count(*) filter (where is_wicket and dismissed_player_id = batter_id) as dismissals,
    round(100.0 * sum(batter_runs) / nullif(count(*) filter (where not is_wide), 0), 2) as strike_rate,
    round(100.0 * count(*) filter (where is_dot_ball and not is_wide)
          / nullif(count(*) filter (where not is_wide), 0), 2)      as dot_ball_pct,
    round(100.0 * count(*) filter (where is_boundary)
          / nullif(count(*) filter (where not is_wide), 0), 2)      as boundary_ball_pct
from d
group by batter_id, format, phase
