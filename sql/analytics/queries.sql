-- Stage 8 SQL analytics library. Engine: DuckDB over the gold layer (schema `gold`) and the dbt
-- models (schema `dbt_analytics`). Run with: python scripts/run_sql_analytics.py
-- Block format: "-- name:" id, "-- group:", "-- question:", then one SELECT ending with ";".
-- Notes: ball-by-ball queries cover only matches that have it (see gold.mart_data_coverage);
-- Super Overs are excluded from regular statistics.

-- name: q01_top_run_scorers_by_format
-- group: batting
-- question: Who has scored the most World Cup runs in each format?
select format, rank, player, matches, runs, average, strike_rate, hundreds from (
  select b.format, row_number() over (partition by b.format order by b.runs desc) as rank,
         p.full_name as player, b.matches, b.runs, b.average, b.strike_rate, b.hundreds
  from gold.mart_batting_career b join gold.dim_players p using (player_id)
) where rank <= 10 order by format, rank;

-- name: q02_highest_individual_scores
-- group: batting
-- question: What are the highest individual innings?
select p.full_name as player, f.runs, f.balls_faced, f.fours, f.sixes, f.format, f.year,
       t.team_name as team, o.team_name as opposition
from gold.fact_player_performances f
join gold.dim_players p using (player_id)
join gold.dim_teams t on t.team_id = f.team_id
join gold.dim_teams o on o.team_id = f.opposition_team_id
where f.did_bat order by f.runs desc, f.balls_faced limit 15;

-- name: q03_most_hundreds
-- group: batting
-- question: Who has the most centuries?
select p.full_name as player, sum(b.hundreds) as hundreds, sum(b.fifties) as fifties, sum(b.runs) as runs
from gold.mart_batting_career b join gold.dim_players p using (player_id)
group by p.full_name having sum(b.hundreds) > 0 order by hundreds desc, runs desc limit 15;

-- name: q04_best_strike_rates
-- group: batting
-- question: Who scores fastest (minimum 300 balls faced)?
select format, player, balls_faced, runs, strike_rate from (
  select b.format, p.full_name as player, b.balls_faced, b.runs, b.strike_rate,
         row_number() over (partition by b.format order by b.strike_rate desc) as rn
  from gold.mart_batting_career b join gold.dim_players p using (player_id)
  where b.balls_faced >= 300
) where rn <= 10 order by format, strike_rate desc;

-- name: q05_most_sixes
-- group: batting
-- question: Who has hit the most sixes?
select p.full_name as player, sum(b.sixes) as sixes, sum(b.fours) as fours, sum(b.runs) as runs
from gold.mart_batting_career b join gold.dim_players p using (player_id)
group by p.full_name order by sixes desc limit 15;

-- name: q06_top_wicket_takers
-- group: bowling
-- question: Who has taken the most wickets in each format?
select format, rank, player, matches, wickets, economy, average, best_figures from (
  select b.format, row_number() over (partition by b.format order by b.wickets desc, b.economy) as rank,
         p.full_name as player, b.matches, b.wickets, b.economy, b.average, b.best_figures
  from gold.mart_bowling_career b join gold.dim_players p using (player_id)
) where rank <= 10 order by format, rank;

-- name: q07_best_bowling_innings
-- group: bowling
-- question: What are the best bowling figures in an innings?
select p.full_name as player, f.wickets, f.runs_conceded, f.overs_bowled, f.format, f.year,
       t.team_name as against
from gold.fact_player_performances f
join gold.dim_players p using (player_id)
join gold.dim_teams t on t.team_id = f.opposition_team_id
where f.did_bowl order by f.wickets desc, f.runs_conceded asc limit 15;

-- name: q08_best_economy
-- group: bowling
-- question: Who is the most economical bowler (minimum 300 balls)?
select format, player, balls_bowled, wickets, economy from (
  select b.format, p.full_name as player, b.balls_bowled, b.wickets, b.economy,
         row_number() over (partition by b.format order by b.economy) as rn
  from gold.mart_bowling_career b join gold.dim_players p using (player_id)
  where b.balls_bowled >= 300
) where rn <= 10 order by format, economy;

-- name: q09_five_wicket_hauls
-- group: bowling
-- question: Who has the most five-wicket hauls?
select p.full_name as player, sum(b.five_wicket_hauls) as five_wicket_hauls,
       sum(b.four_wicket_hauls) as four_wicket_hauls, sum(b.wickets) as wickets
from gold.mart_bowling_career b join gold.dim_players p using (player_id)
group by p.full_name having sum(b.five_wicket_hauls) > 0 order by 2 desc, wickets desc limit 15;

-- name: q10_players_of_the_tournament
-- group: awards
-- question: How did each Player of the Tournament perform?
select t.tournament_name, p.full_name as player_of_tournament,
       coalesce(bt.runs, 0) as runs, coalesce(bw.wickets, 0) as wickets, bt.average as bat_average
from gold.dim_tournaments t
join gold.dim_players p on p.player_id = t.player_of_tournament_id
left join gold.mart_batting bt on bt.player_id = t.player_of_tournament_id and bt.tournament_id = t.tournament_id
left join gold.mart_bowling bw on bw.player_id = t.player_of_tournament_id and bw.tournament_id = t.tournament_id
order by t.format, t.year;

-- name: q11_titles_by_team
-- group: teams
-- question: Which teams have won the most World Cups?
select t.team_name, d.format, count(*) as titles
from gold.dim_tournaments d join gold.dim_teams t on t.team_id = d.winner_team_id
group by t.team_name, d.format order by titles desc, d.format, t.team_name;

-- name: q12_team_win_percentage
-- group: teams
-- question: Which teams win the highest share of their completed matches (min 15 matches)?
select format, team_name, matches, wins, win_pct from (
  select m.format, t.team_name, count(*) as matches,
         count(*) filter (where m.winner_id = t.team_id) as wins,
         round(100.0 * count(*) filter (where m.winner_id = t.team_id) / count(*), 1) as win_pct
  from gold.fact_matches m
  join gold.dim_teams t on t.team_id in (m.team1_id, m.team2_id)
  where m.is_completed and not m.is_walkover
  group by m.format, t.team_name
) where matches >= 15 order by format, win_pct desc;

-- name: q13_highest_team_totals
-- group: teams
-- question: What are the highest innings totals?
select t.team_name, i.total_runs, i.wickets, i.overs, i.format, i.year, o.team_name as against
from gold.fact_innings i
join gold.dim_teams t on t.team_id = i.batting_team_id
join gold.dim_teams o on o.team_id = i.bowling_team_id
where not i.is_super_over order by i.total_runs desc limit 15;

-- name: q14_lowest_all_out_totals
-- group: teams
-- question: What are the lowest completed innings (all out)?
select t.team_name, i.total_runs, i.wickets, i.overs, i.format, i.year, o.team_name as against
from gold.fact_innings i
join gold.dim_teams t on t.team_id = i.batting_team_id
join gold.dim_teams o on o.team_id = i.bowling_team_id
where not i.is_super_over and i.wickets = 10 order by i.total_runs asc limit 15;

-- name: q15_biggest_wins_by_runs
-- group: matches
-- question: What are the biggest victories by runs?
select m.format, m.year, w.team_name as winner, l.team_name as loser, m.margin_value as runs_margin, m.is_dls
from gold.fact_matches m
join gold.dim_teams w on w.team_id = m.winner_id
join gold.dim_teams l on l.team_id = m.loser_id
where m.margin_type = 'runs' order by m.margin_value desc limit 15;

-- name: q16_closest_finishes
-- group: matches
-- question: Which matches were decided by the narrowest margins?
select m.format, m.year, m.match_date, w.team_name as winner, l.team_name as loser, m.margin_type, m.margin_value
from gold.fact_matches m
join gold.dim_teams w on w.team_id = m.winner_id
join gold.dim_teams l on l.team_id = m.loser_id
where (m.margin_type = 'runs' and m.margin_value <= 2) or (m.margin_type = 'wickets' and m.margin_value = 1)
order by m.match_date;

-- name: q17_bat_first_vs_chase_by_era
-- group: matches
-- question: Is batting first or chasing more successful, and has that changed?
select format, year, count(*) as matches,
       count(*) filter (where winner_id = batting_first_team_id) as bat_first_wins,
       count(*) filter (where winner_id = batting_second_team_id) as chase_wins,
       round(100.0 * count(*) filter (where winner_id = batting_first_team_id)
             / nullif(count(*) filter (where winner_id is not null), 0), 1) as bat_first_win_pct
from gold.fact_matches where is_completed and not is_walkover
group by format, year order by format, year;

-- name: q18_toss_decisions_and_value
-- group: matches
-- question: What do captains choose at the toss, and does winning it help?
select format, year, count(*) as matches,
       round(100.0 * count(*) filter (where toss_decision = 'field') / count(*), 1) as chose_field_pct,
       round(100.0 * count(*) filter (where winner_id = toss_winner_id)
             / nullif(count(*) filter (where winner_id is not null), 0), 1) as toss_winner_win_pct
from gold.fact_matches where toss_winner_id is not null and is_completed
group by format, year order by format, year;

-- name: q19_top_rivalries
-- group: teams
-- question: Which pairings have met most often, and who leads?
select h.format, a.team_name as team_a, b.team_name as team_b, h.matches, h.team_a_wins, h.team_b_wins, h.no_winner
from dbt_analytics.an_head_to_head h
join gold.dim_teams a on a.team_id = h.team_a_id
join gold.dim_teams b on b.team_id = h.team_b_id
order by h.matches desc, h.format limit 20;

-- name: q20_furthest_progress
-- group: teams
-- question: How far did each team go in each edition (champions and finalists)?
select tp.format, tp.year, t.team_name, tp.furthest_stage, tp.wins, tp.matches, tp.is_champion
from gold.mart_team_performance tp join gold.dim_teams t using (team_id)
where tp.furthest_stage in ('Final') order by tp.format, tp.year, tp.is_champion desc;

-- name: q21_scoring_trend_by_edition
-- group: tournaments
-- question: How has scoring changed edition by edition?
select format, year, matches, runs_per_match, avg_first_innings_score, bat_first_win_pct
from gold.mart_tournament_summary order by format, year;

-- name: q22_boundaries_per_match
-- group: tournaments
-- question: How has boundary hitting grown?
select format, year, round(1.0 * fours / matches, 1) as fours_per_match,
       round(1.0 * sixes / matches, 1) as sixes_per_match, sixes
from gold.mart_tournament_summary order by format, year;

-- name: q23_ties_dls_super_overs
-- group: tournaments
-- question: Which editions had ties, DLS-affected matches or Super Overs?
select tournament_name, matches, ties, dls_matches, super_overs
from gold.mart_tournament_summary where ties + dls_matches + super_overs > 0 order by format, year;

-- name: q24_ball_by_ball_coverage
-- group: data_quality
-- question: Where is ball-by-ball data available, and how much of each edition?
select tournament_name, played_matches, played_with_ball_by_ball, played_without_ball_by_ball,
       ball_by_ball_coverage_pct_of_played as coverage_pct, ball_by_ball_source
from gold.mart_data_coverage order by format, year;

-- name: q25_venue_scoring_profile
-- group: venues
-- question: Which grounds are the highest scoring (min 8 matches)?
select venue_name, city, format, matches, avg_first_innings_runs, bat_first_win_pct, toss_winner_win_pct
from dbt_analytics.an_venue_profile where matches >= 8 order by format, avg_first_innings_runs desc;

-- name: q26_busiest_venues
-- group: venues
-- question: Which grounds have hosted the most World Cup matches?
select venue_name, city, matches, first_year, last_year from gold.dim_venues order by matches desc limit 15;

-- name: q27_best_powerplay_batters
-- group: phases
-- question: Who bats best in the T20 powerplay (min 200 balls)?
select p.full_name as player, b.balls_faced, b.runs, b.strike_rate, b.boundary_ball_pct, b.dismissals
from dbt_analytics.an_player_phase_batting b join gold.dim_players p using (player_id)
where b.format = 'T20' and b.phase = 'powerplay' and b.balls_faced >= 200 order by b.strike_rate desc limit 15;

-- name: q28_best_death_overs_batters
-- group: phases
-- question: Who finishes best in the death overs (min 150 balls)?
select b.format, p.full_name as player, b.balls_faced, b.runs, b.strike_rate, b.sixes
from dbt_analytics.an_player_phase_batting b join gold.dim_players p using (player_id)
where b.phase = 'death' and b.balls_faced >= 150 order by b.strike_rate desc limit 20;

-- name: q29_best_death_bowlers
-- group: phases
-- question: Who bowls best at the death (min 120 legal balls)?
select b.format, p.full_name as player, b.legal_balls, b.runs_conceded, b.wickets, b.economy, b.dot_ball_pct
from dbt_analytics.an_player_phase_bowling b join gold.dim_players p using (player_id)
where b.phase = 'death' and b.legal_balls >= 120 order by b.economy limit 20;

-- name: q30_run_rate_by_phase_and_edition
-- group: phases
-- question: How does scoring speed vary by phase and edition?
select format, year, phase, round(6.0 * sum(total_runs) / nullif(count(*) filter (where is_legal_ball), 0), 2) as run_rate,
       round(100.0 * avg(case when is_dot_ball then 1.0 else 0.0 end), 1) as dot_ball_pct
from gold.fact_deliveries where not is_super_over and phase in ('powerplay', 'middle', 'death')
group by format, year, phase order by format, year, phase;

-- name: q31_powerplay_wicket_takers
-- group: phases
-- question: Who takes the most wickets in the T20 powerplay?
select p.full_name as player, b.wickets, b.legal_balls, b.economy
from dbt_analytics.an_player_phase_bowling b join gold.dim_players p using (player_id)
where b.format = 'T20' and b.phase = 'powerplay' order by b.wickets desc, b.economy limit 15;

-- name: q32_top_three_scorers_per_edition
-- group: advanced
-- question: Who were the three leading run scorers in each tournament? (window rank)
select tournament_name, rank, player, runs, average, strike_rate from (
  select t.tournament_name, t.format, t.year, p.full_name as player, b.runs, b.average, b.strike_rate,
         rank() over (partition by b.tournament_id order by b.runs desc) as rank
  from gold.mart_batting b
  join gold.dim_players p using (player_id)
  join gold.dim_tournaments t using (tournament_id)
) where rank <= 3 order by format, year, rank;

-- name: q33_form_change_between_editions
-- group: advanced
-- question: How did a batter's average change from their previous World Cup? (LAG)
select player, tournament_id, runs, average, prev_average, round(average - prev_average, 2) as change from (
  select p.full_name as player, b.tournament_id, b.runs, b.average,
         lag(b.average) over (partition by b.player_id, b.format order by b.year) as prev_average,
         b.innings
  from gold.mart_batting b join gold.dim_players p using (player_id)
  where b.innings >= 5
) where prev_average is not null order by change desc limit 15;

-- name: q34_chase_success_by_target
-- group: advanced
-- question: How does chase success depend on the size of the target?
with c as (
  select format, target, winner_id = batting_second_team_id as chased,
         case when format = 'T20' then (target // 20) * 20 else (target // 40) * 40 end as bucket
  from gold.fact_matches
  where is_completed and not is_dls and not is_tie and winner_id is not null and target is not null
)
select format, bucket as target_from, count(*) as matches,
       round(100.0 * avg(case when chased then 1.0 else 0.0 end), 1) as chase_win_pct
from c group by format, bucket order by format, bucket;

-- name: q35_most_editions_played
-- group: players
-- question: Who has played in the most different World Cups?
select p.full_name as player, count(distinct f.tournament_id) as tournaments, count(*) as matches,
       min(f.year) as first_year, max(f.year) as last_year
from gold.fact_player_performances f join gold.dim_players p using (player_id)
group by p.full_name order by tournaments desc, matches desc limit 15;

-- name: q36_player_of_match_leaders
-- group: awards
-- question: Who has won the most Player of the Match awards?
select p.full_name as player, count(*) as awards, min(m.year) as first_year, max(m.year) as last_year
from gold.fact_matches m join gold.dim_players p on p.player_id = m.player_of_match_id
group by p.full_name order by awards desc, player limit 15;

-- name: q37_all_round_impact_leaders
-- group: players
-- question: Who has had the biggest all-round impact in a single tournament?
select full_name, tournament_id, runs, wickets, dismissals_effected, player_of_match_awards, impact_points
from dbt_analytics.an_player_tournament_impact order by impact_points desc limit 15;

-- name: q38_dot_ball_pressure_by_over
-- group: phases
-- question: In which overs are dot balls most common in T20?
select over_number, count(*) as balls, round(100.0 * avg(case when is_dot_ball then 1.0 else 0.0 end), 1) as dot_ball_pct,
       round(6.0 * sum(total_runs) / count(*) filter (where is_legal_ball), 2) as run_rate
from gold.fact_deliveries where format = 'T20' and not is_super_over and over_number <= 20
group by over_number order by over_number;

-- name: q39_dismissal_types
-- group: bowling
-- question: How are batters dismissed in each format?
select m.format, d.dismissal_type, count(*) as dismissals,
       round(100.0 * count(*) / sum(count(*)) over (partition by m.format), 1) as pct
from gold.fact_deliveries d join gold.fact_matches m using (match_id)
where d.is_wicket and not d.is_super_over group by m.format, d.dismissal_type order by m.format, dismissals desc;

-- name: q40_hosts_and_finalists
-- group: tournaments
-- question: Who hosted each edition and who reached the final?
select d.tournament_name, d.host_country, d.winner, d.runner_up
from gold.dim_tournaments d order by d.format, d.year;
