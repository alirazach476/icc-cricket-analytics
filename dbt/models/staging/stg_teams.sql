select
    team_id,
    team_name,
    short_name,
    country_code,
    source_team_id,
    source_id,
    source_url,
    collected_at
from {{ source('warehouse', 'teams') }}
