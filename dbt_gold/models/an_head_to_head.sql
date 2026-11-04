-- Team vs team record over all World Cup meetings (both orderings folded into one row per pair).
with m as (
    select
        format,
        least(team1_id, team2_id)    as team_a_id,
        greatest(team1_id, team2_id) as team_b_id,
        winner_id
    from {{ source('gold', 'fact_matches') }}
)
select
    md5(format || '|' || team_a_id || '|' || team_b_id) as head_to_head_key,
    format, team_a_id, team_b_id,
    count(*)                                        as matches,
    count(*) filter (where winner_id = team_a_id)   as team_a_wins,
    count(*) filter (where winner_id = team_b_id)   as team_b_wins,
    count(*) filter (where winner_id is null)       as no_winner
from m
group by format, team_a_id, team_b_id
