with matches as (
    select * from {{ ref('stg_matches') }}
),
teams as (
    select team_id, team_name, short_name from {{ ref('stg_teams') }}
),
tournaments as (
    select tournament_id, tournament_name, year, format from {{ ref('stg_tournaments') }}
),
players as (
    select player_id, full_name from {{ ref('stg_players') }}
)

select
    m.match_id,
    m.tournament_id,
    t.tournament_name,
    t.year as tournament_year,
    t.format as tournament_format,
    m.match_number,
    m.match_stage,
    m.match_date,
    m.venue,
    m.city,
    m.team1_id,
    t1.team_name as team1_name,
    m.team2_id,
    t2.team_name as team2_name,
    m.toss_winner_id,
    tw.team_name as toss_winner_name,
    m.toss_decision,
    m.winner_id,
    w.team_name as winner_name,
    m.result_type,
    m.result_margin,
    m.player_of_match_id,
    pom.full_name as player_of_match_name,
    m.ball_by_ball_status,
    m.scorecard_status,
    m.match_status,
    m.scorecard_url,
    m.commentary_url
from matches as m
left join tournaments as t on t.tournament_id = m.tournament_id
left join teams as t1 on t1.team_id = m.team1_id
left join teams as t2 on t2.team_id = m.team2_id
left join teams as tw on tw.team_id = m.toss_winner_id
left join teams as w on w.team_id = m.winner_id
left join players as pom on pom.player_id = m.player_of_match_id
