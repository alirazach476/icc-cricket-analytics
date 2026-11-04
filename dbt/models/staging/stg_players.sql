select
    player_id,
    full_name,
    source_name,
    source_player_id,
    batting_style,
    bowling_style,
    date_of_birth,
    source_id,
    source_url,
    collected_at
from {{ source('warehouse', 'players') }}
