{% macro tournament_filter(alias='m') -%}
{%- if var('tournament_id', none) -%}
  and {{ alias }}.tournament_id = '{{ var("tournament_id") }}'
{%- endif -%}
{%- endmacro %}
