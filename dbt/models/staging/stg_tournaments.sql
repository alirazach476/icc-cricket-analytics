with source as (
    select * from {{ source('warehouse', 'tournaments') }}
)

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
    completion_status,
    metadata_notes,
    source_id,
    source_url,
    collected_at
from source
where 1 = 1
  {% if var('tournament_id', none) %}
  and tournament_id = '{{ var("tournament_id") }}'
  {% endif %}
