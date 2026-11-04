-- How each ground plays: scoring level, batting-first advantage, toss effect (completed, non-walkover).
select
    v.venue_id, v.venue_name, v.city, m.format,
    count(*)                                                     as matches,
    round(avg(m.first_innings_runs), 1)                          as avg_first_innings_runs,
    round(avg(m.second_innings_runs), 1)                         as avg_second_innings_runs,
    round(100.0 * count(*) filter (where m.winner_id = m.batting_first_team_id)
          / nullif(count(*) filter (where m.winner_id is not null), 0), 1) as bat_first_win_pct,
    round(100.0 * count(*) filter (where m.winner_id = m.toss_winner_id)
          / nullif(count(*) filter (where m.winner_id is not null and m.toss_winner_id is not null), 0), 1) as toss_winner_win_pct
from {{ source('gold', 'fact_matches') }} m
join {{ source('gold', 'dim_venues') }} v using (venue_id)
where m.is_completed and not m.is_walkover
group by v.venue_id, v.venue_name, v.city, m.format
