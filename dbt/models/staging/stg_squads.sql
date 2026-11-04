select
    squad_id,
    tournament_id,
    team_id,
    player_id,
    role_code,
    is_captain,
    is_wicketkeeper,
    playing_roles,
    announced_at,
    is_withdrawn,
    note,
    source_url,
    collected_at
from {{ source('warehouse', 'squads') }}
