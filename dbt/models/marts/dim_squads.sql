-- One row per player per team per tournament. is_withdrawn marks players who were
-- replaced or withdrew; filter them out for the final squad.
select
    q.squad_id,
    q.tournament_id,
    t.tournament_name,
    t.year,
    t.format,
    q.team_id,
    tm.team_name,
    q.player_id,
    p.full_name as player_name,
    q.role_code,
    q.is_captain,
    q.is_wicketkeeper,
    q.playing_roles,
    q.announced_at,
    q.is_withdrawn,
    q.note
from {{ ref('stg_squads') }} q
join {{ ref('stg_tournaments') }} t on t.tournament_id = q.tournament_id
join {{ ref('stg_teams') }} tm on tm.team_id = q.team_id
join {{ ref('stg_players') }} p on p.player_id = q.player_id
