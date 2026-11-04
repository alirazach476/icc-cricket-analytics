select
    player_id,
    full_name,
    source_name,
    source_player_id,
    batting_style,
    bowling_style,
    date_of_birth
from {{ ref('stg_players') }}
