with matches as (
    select match_id from {{ ref('stg_matches') }}
)

select
    f.fielding_scorecard_id,
    f.match_id,
    f.player_id,
    f.player_name,
    f.team_id,
    f.catches,
    f.run_outs,
    f.stumpings,
    f.source_id,
    f.source_url,
    f.collected_at
from {{ source('warehouse', 'fielding_scorecards') }} as f
inner join matches as m on m.match_id = f.match_id
