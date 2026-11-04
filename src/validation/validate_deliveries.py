"""Delivery-level rules (ball-by-ball). Only matches that have deliveries are in scope."""

from __future__ import annotations

from src.validation.rules import Rule

BASE = (
    "deliveries d join matches m on m.match_id = d.match_id "
    "join tournaments t on t.tournament_id = m.tournament_id"
)
KEY = "d.delivery_id"

RULES: list[Rule] = [
    Rule(
        "deliveries.unique_sequence",
        "deliveries",
        "uniqueness",
        "critical",
        "(innings, delivery_sequence) occurs once",
        "(select d.delivery_id, m.tournament_id, count(*) over (partition by d.innings_id, "
        "d.delivery_sequence) c from deliveries d join matches m on m.match_id = d.match_id) x",
        "x.c > 1",
        tid="x.tournament_id",
        key="x.delivery_id",
    ),
    Rule(
        "deliveries.players_present",
        "deliveries",
        "completeness",
        "critical",
        "batter and bowler are recorded",
        BASE,
        "d.batter_id is null or d.bowler_id is null",
        key=KEY,
    ),
    Rule(
        "deliveries.runs_valid",
        "deliveries",
        "validity",
        "critical",
        "batter, extra and total runs are present and not negative",
        BASE,
        "d.batter_runs is null or d.extra_runs is null or d.total_runs is null "
        "or d.batter_runs < 0 or d.extra_runs < 0 or d.total_runs < 0",
        key=KEY,
    ),
    Rule(
        "deliveries.over_in_range",
        "deliveries",
        "validity",
        "major",
        "over number is within the format (1-based: ODI 1-50, T20 1-20)",
        BASE,
        "d.over_number < 1 or d.over_number > case when t.format = 'ODI' then 50 else 20 end",
        key=KEY,
    ),
    Rule(
        "deliveries.batter_not_non_striker",
        "deliveries",
        "validity",
        "major",
        "batter and non-striker are different players",
        BASE,
        "d.batter_id = d.non_striker_id",
        where="d.non_striker_id is not null",
        key=KEY,
    ),
    Rule(
        "deliveries.total_is_batter_plus_extras",
        "deliveries",
        "consistency",
        "critical",
        "total runs = batter runs + extra runs",
        BASE,
        "d.total_runs <> d.batter_runs + d.extra_runs",
        key=KEY,
    ),
    Rule(
        "deliveries.legal_number_matches_flags",
        "deliveries",
        "consistency",
        "major",
        "legal_ball_number is blank exactly for wides (project definition numbers no-balls as balls faced)",
        BASE,
        "(d.legal_ball_number is null) <> coalesce(d.is_wide, false)",
        key=KEY,
        note="legal_ball_number counts no-balls, so it is NOT balls bowled; use is_wide/is_no_ball for overs",
    ),
    Rule(
        "deliveries.extras_type_matches_runs",
        "deliveries",
        "consistency",
        "major",
        "extras_type is set exactly when extra runs were scored",
        BASE,
        "(d.extras_type is not null) <> (d.extra_runs > 0)",
        key=KEY,
    ),
    Rule(
        "deliveries.wicket_has_dismissal",
        "deliveries",
        "consistency",
        "major",
        "a wicket delivery records the dismissal type and the dismissed player",
        BASE,
        "d.dismissal_type is null or d.dismissed_player_id is null",
        where="d.is_wicket",
        key=KEY,
    ),
    Rule(
        "deliveries.non_wicket_has_no_dismissal",
        "deliveries",
        "consistency",
        "major",
        "a non-wicket delivery has no dismissal fields",
        BASE,
        "d.dismissal_type is not null or d.dismissed_player_id is not null",
        where="not coalesce(d.is_wicket, false)",
        key=KEY,
    ),
]
