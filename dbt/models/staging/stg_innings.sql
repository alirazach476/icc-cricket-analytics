with matches as (
    select match_id from {{ ref('stg_matches') }}
)

select
    i.innings_id,
    i.match_id,
    i.innings_number,
    i.innings_type,
    i.batting_team_id,
    i.bowling_team_id,
    i.total_runs,
    i.wickets,
    i.overs,
    i.extras,
    i.declared,
    i.is_super_over,
    i.target,
    i.source_id,
    i.source_url,
    i.collected_at
from {{ source('warehouse', 'innings') }} as i
inner join matches as m on m.match_id = i.match_id
