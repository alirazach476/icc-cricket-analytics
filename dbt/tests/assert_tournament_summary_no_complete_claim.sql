-- Ensure coverage mart never claims complete coverage
select *
from {{ ref('mart_tournament_summary') }}
where claims_complete_coverage is distinct from false
