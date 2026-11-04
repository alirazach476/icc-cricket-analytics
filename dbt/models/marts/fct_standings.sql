select
    s.standing_id,
    s.tournament_id,
    t.tournament_name,
    t.year,
    t.format,
    s.group_name,
    s.position,
    s.team_id,
    tm.team_name,
    s.matches_played,
    s.wins,
    s.losses,
    s.ties,
    s.no_results,
    s.points,
    s.net_run_rate,
    s.qualified
from {{ ref('stg_standings') }} s
join {{ ref('stg_tournaments') }} t on t.tournament_id = s.tournament_id
join {{ ref('stg_teams') }} tm on tm.team_id = s.team_id
