select
    b.batting_scorecard_id,
    b.match_id,
    m.tournament_id,
    m.match_date,
    b.innings_id,
    b.innings_number,
    b.player_id,
    coalesce(p.full_name, b.player_name) as player_name,
    b.team_id,
    b.batting_position,
    b.runs,
    b.balls_faced,
    b.fours,
    b.sixes,
    b.strike_rate,
    b.dismissal,
    b.dismissal_type,
    b.dismissed_by,
    b.fielder
from {{ ref('stg_batting_scorecards') }} as b
inner join {{ ref('stg_matches') }} as m on m.match_id = b.match_id
left join {{ ref('stg_players') }} as p on p.player_id = b.player_id
