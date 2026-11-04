with matches as (
    select match_id from {{ ref('stg_matches') }}
)

select
    b.bowling_scorecard_id,
    b.match_id,
    b.innings_id,
    b.innings_number,
    b.player_id,
    b.player_name,
    b.team_id,
    b.overs,
    b.maidens,
    b.runs_conceded,
    b.wickets,
    b.economy,
    b.dots,
    b.wides,
    b.no_balls,
    b.source_id,
    b.source_url,
    b.collected_at
from {{ source('warehouse', 'bowling_scorecards') }} as b
inner join matches as m on m.match_id = b.match_id
