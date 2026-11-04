select
    tournament_id,
    tournament_name,
    year,
    format,
    gender,
    host_country,
    start_date,
    end_date,
    winner,
    runner_up,
    number_of_teams,
    number_of_matches,
    collection_status,
    completion_status
from {{ ref('stg_tournaments') }}
