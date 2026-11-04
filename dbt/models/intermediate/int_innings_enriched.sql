with innings as (
    select * from {{ ref('stg_innings') }}
),
matches as (
    select match_id, tournament_id, match_date from {{ ref('stg_matches') }}
),
teams as (
    select team_id, team_name from {{ ref('stg_teams') }}
)

select
    i.innings_id,
    i.match_id,
    m.tournament_id,
    m.match_date,
    i.innings_number,
    i.innings_type,
    i.batting_team_id,
    bt.team_name as batting_team_name,
    i.bowling_team_id,
    bowl.team_name as bowling_team_name,
    i.total_runs,
    i.wickets,
    i.overs,
    i.extras,
    i.declared,
    i.is_super_over,
    i.target
from innings as i
inner join matches as m on m.match_id = i.match_id
left join teams as bt on bt.team_id = i.batting_team_id
left join teams as bowl on bowl.team_id = i.bowling_team_id
