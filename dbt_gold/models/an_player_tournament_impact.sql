-- One row per player per tournament combining batting, bowling, fielding and awards.
select
    md5(p.player_id || '|' || p.tournament_id)                    as impact_key,
    p.player_id, pl.full_name, p.tournament_id, p.format, p.year,
    count(*)                                                       as matches,
    coalesce(sum(p.runs), 0)                                       as runs,
    coalesce(sum(p.balls_faced), 0)                                as balls_faced,
    coalesce(sum(p.wickets), 0)                                    as wickets,
    coalesce(sum(p.catches), 0) + coalesce(sum(p.run_outs), 0) + coalesce(sum(p.stumpings), 0) as dismissals_effected,
    count(*) filter (where p.is_player_of_match)                   as player_of_match_awards,
    -- simple, transparent all-round index: runs + 20 per wicket + 10 per fielding dismissal
    coalesce(sum(p.runs), 0) + 20 * coalesce(sum(p.wickets), 0)
      + 10 * (coalesce(sum(p.catches), 0) + coalesce(sum(p.run_outs), 0) + coalesce(sum(p.stumpings), 0)) as impact_points
from {{ source('gold', 'fact_player_performances') }} p
join {{ source('gold', 'dim_players') }} pl using (player_id)
group by p.player_id, pl.full_name, p.tournament_id, p.format, p.year
