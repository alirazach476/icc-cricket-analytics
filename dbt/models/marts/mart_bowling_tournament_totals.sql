-- Aggregates only over loaded scorecard rows (no fabricated careers).
select
    tournament_id,
    player_id,
    max(player_name) as player_name,
    count(*) as innings_bowled,
    sum(coalesce(wickets, 0)) as wickets,
    sum(coalesce(runs_conceded, 0)) as runs_conceded,
    sum(coalesce(maidens, 0)) as maidens,
    sum(coalesce(wides, 0)) as wides,
    sum(coalesce(no_balls, 0)) as no_balls
from {{ ref('fct_bowling_scorecards') }}
group by tournament_id, player_id
