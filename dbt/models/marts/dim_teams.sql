select
    team_id,
    team_name,
    short_name,
    country_code,
    source_team_id
from {{ ref('stg_teams') }}
