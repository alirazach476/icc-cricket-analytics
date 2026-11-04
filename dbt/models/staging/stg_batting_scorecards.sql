with matches as (
    select match_id from {{ ref('stg_matches') }}
)

select
    b.batting_scorecard_id,
    b.match_id,
    b.innings_id,
    b.innings_number,
    b.player_id,
    b.player_name,
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
    b.fielder,
    b.source_id,
    b.source_url,
    b.collected_at
from {{ source('warehouse', 'batting_scorecards') }} as b
inner join matches as m on m.match_id = b.match_id
