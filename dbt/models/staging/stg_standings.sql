select
    standing_id,
    tournament_id,
    group_name,
    team_id,
    matches_played,
    wins,
    losses,
    ties,
    no_results,
    points,
    net_run_rate,
    position,
    qualified,
    source_url,
    collected_at
from {{ source('warehouse', 'standings') }}
