with source as (
    select * from {{ source('warehouse', 'matches') }}
)

select
    match_id,
    tournament_id,
    source_match_id,
    match_number,
    match_stage,
    match_type,
    match_date,
    start_time,
    venue,
    city,
    team1_id,
    team2_id,
    toss_winner_id,
    toss_decision,
    winner_id,
    result_type,
    result_margin,
    player_of_match_id,
    umpires,
    match_referee,
    scorecard_url,
    commentary_url,
    ball_by_ball_status,
    scorecard_status,
    match_status,
    source_id,
    source_url,
    collected_at
from source
where 1 = 1
  {% if var('tournament_id', none) %}
  and tournament_id = '{{ var("tournament_id") }}'
  {% endif %}
