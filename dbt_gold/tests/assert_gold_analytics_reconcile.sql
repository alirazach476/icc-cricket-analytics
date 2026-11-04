-- Reconciliation of the analytics models back to gold facts. Returns a row per broken check.
select 'phase_balls' as check_name, a.n as model_value, b.n as gold_value
from (select sum(balls_faced) n from {{ ref('an_player_phase_batting') }}) a,
     (select count(*) filter (where not is_wide) n from {{ source('gold', 'fact_deliveries') }}
       where not is_super_over and phase in ('powerplay', 'middle', 'death')) b
where a.n <> b.n
union all
select 'phase_runs', a.n, b.n
from (select sum(runs) n from {{ ref('an_player_phase_batting') }}) a,
     (select sum(batter_runs) n from {{ source('gold', 'fact_deliveries') }}
       where not is_super_over and phase in ('powerplay', 'middle', 'death')) b
where a.n <> b.n
union all
select 'head_to_head_matches', a.n, b.n
from (select sum(matches) n from {{ ref('an_head_to_head') }}) a,
     (select count(*) n from {{ source('gold', 'fact_matches') }}) b
where a.n <> b.n
union all
select 'bowler_wickets_le_wickets_fallen', a.n, b.n
from (select sum(wickets) n from {{ ref('an_player_phase_bowling') }}) a,
     (select count(*) n from {{ source('gold', 'fact_deliveries') }}
       where is_wicket and not is_super_over) b
where a.n > b.n
