-- Aggregates only over loaded scorecard rows (no fabricated careers).
select
    tournament_id,
    player_id,
    max(player_name) as player_name,
    count(*) as innings_batted,
    sum(coalesce(runs, 0)) as runs,
    sum(coalesce(balls_faced, 0)) as balls_faced,
    sum(coalesce(fours, 0)) as fours,
    sum(coalesce(sixes, 0)) as sixes,
    max(coalesce(runs, 0)) as high_score
from {{ ref('fct_batting_scorecards') }}
group by tournament_id, player_id
