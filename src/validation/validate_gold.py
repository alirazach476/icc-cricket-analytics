# ruff: noqa: E501
"""Data-quality rules for the resolved analytics (gold) layer, run against ``analytics.*``.

The Stage 3 rules check the as-collected operational tables. These rules check what the database
*cannot* guarantee with constraints (primary keys, foreign keys and column checks already do that):
reconciliation between facts, identity resolution, and what is genuinely missing at source.
"""

from __future__ import annotations

from src.validation.rules import Rule

A = "analytics"
M = f"{A}.fact_matches m"
I = f"{A}.fact_innings i"  # noqa: E741
D = f"{A}.fact_deliveries d"

RULES: list[Rule] = [
    # ------------------------------------------------------------------ completeness
    Rule(
        "gold.match_has_result",
        "gold.fact_matches",
        "completeness",
        "critical",
        "completed match has a winner, or is a recorded tie",
        M,
        "winner_id is null and not is_tie",
        "is_completed",
        key="m.match_id",
        note="open genuine ties have is_tie=true and are not counted here",
    ),
    Rule(
        "gold.match_has_scores",
        "gold.fact_matches",
        "completeness",
        "major",
        "completed non-walkover match has both innings totals",
        M,
        "first_innings_runs is null or second_innings_runs is null",
        "is_completed and not is_walkover",
        key="m.match_id",
    ),
    Rule(
        "gold.match_has_venue_city",
        "gold.fact_matches",
        "completeness",
        "minor",
        "match has a venue city",
        M,
        "city is null",
        key="m.match_id",
    ),
    Rule(
        "gold.completed_match_has_player_of_match",
        "gold.fact_matches",
        "completeness",
        "minor",
        "completed non-walkover match names a player of the match",
        M,
        "player_of_match_id is null",
        "is_completed and not is_walkover",
        key="m.match_id",
        note="some early-edition pages do not name one",
    ),
    # ------------------------------------------------------------------ uniqueness
    Rule(
        "gold.venue_unique_name",
        "gold.dim_venues",
        "uniqueness",
        "major",
        "no two venues share a canonical name in the same city",
        f"{A}.dim_venues v",
        f"(select count(*) from {A}.dim_venues o where o.venue_name = v.venue_name "
        "and coalesce(o.city, '') = coalesce(v.city, '')) > 1",
        tid="'(global)'",
        key="v.venue_id",
    ),
    Rule(
        "gold.player_unique_name_dob",
        "gold.dim_players",
        "uniqueness",
        "minor",
        "player full names are unique (homonyms are listed, not merged)",
        f"{A}.dim_players p",
        f"(select count(*) from {A}.dim_players o where o.full_name = p.full_name) > 1",
        tid="'(global)'",
        key="p.player_id",
        note="different people can share a name; flagged for review only",
    ),
    # ------------------------------------------------------------------ validity
    Rule(
        "gold.delivery_wicket_has_dismissal",
        "gold.fact_deliveries",
        "validity",
        "major",
        "a wicket ball names the dismissal type and dismissed player",
        f"{D} join {M} on m.match_id = d.match_id",
        "dismissal_type is null or dismissed_player_id is null",
        "d.is_wicket",
        key="d.delivery_id",
    ),
    Rule(
        "gold.delivery_boundary_flags",
        "gold.fact_deliveries",
        "validity",
        "major",
        "four/six flags agree with batter runs",
        f"{D} join {M} on m.match_id = d.match_id",
        "(d.is_four and d.batter_runs <> 4) or (d.is_six and d.batter_runs <> 6)",
        key="d.delivery_id",
    ),
    Rule(
        "gold.delivery_wide_no_legal",
        "gold.fact_deliveries",
        "validity",
        "major",
        "wides and no-balls are never counted as legal deliveries",
        f"{D} join {M} on m.match_id = d.match_id",
        "d.is_legal_ball and (d.is_wide or d.is_no_ball)",
        key="d.delivery_id",
    ),
    Rule(
        "gold.performance_strike_rate",
        "gold.fact_player_performances",
        "validity",
        "minor",
        "batting strike rate within 0-600",
        f"{A}.fact_player_performances p join {M} on m.match_id = p.match_id",
        "p.strike_rate < 0 or p.strike_rate > 600",
        "p.strike_rate is not null",
        key="p.match_id || '/' || p.player_id",
    ),
    # ------------------------------------------------------------------ consistency
    Rule(
        "gold.innings_runs_match_deliveries",
        "gold.fact_innings",
        "consistency",
        "critical",
        "innings total equals the sum of its deliveries (ball-by-ball innings)",
        f"{I} join {M} on m.match_id = i.match_id "
        f"join (select innings_id, sum(total_runs) r from {A}.fact_deliveries group by 1) x "
        "on x.innings_id = i.innings_id",
        "i.total_runs is distinct from x.r",
        key="i.innings_id",
    ),
    Rule(
        "gold.innings_wickets_match_deliveries",
        "gold.fact_innings",
        "consistency",
        "critical",
        "innings wickets equal the wickets recorded on its deliveries",
        f"{I} join {M} on m.match_id = i.match_id "
        f"join (select innings_id, sum(case when is_wicket then 1 else 0 end) w "
        f"from {A}.fact_deliveries group by 1) x on x.innings_id = i.innings_id",
        "i.wickets is distinct from x.w",
        key="i.innings_id",
        note="Bangladesh v Sri Lanka 2023-11-06: Mathews was timed out, which the scorecard counts as a wicket but no ball was bowled, so it has no delivery row",
    ),
    Rule(
        "gold.match_winner_has_more_runs",
        "gold.fact_matches",
        "consistency",
        "major",
        "the winner scored more runs than the loser (no DLS, tie or super over)",
        M,
        "(winner_id = batting_first_team_id and first_innings_runs <= second_innings_runs) "
        "or (winner_id = batting_second_team_id and second_innings_runs <= first_innings_runs)",
        "is_completed and not is_dls and not is_tie and not went_to_super_over "
        "and not is_walkover and winner_id is not null "
        "and first_innings_runs is not null and second_innings_runs is not null",
        key="m.match_id",
        note="matches decided on run rate or a bowl-out can legitimately differ",
    ),
    Rule(
        "gold.performance_runs_match_scorecard_total",
        "gold.fact_innings",
        "consistency",
        "major",
        "batters' runs + extras equal the innings total (scorecard reconciliation)",
        f"{I} join {M} on m.match_id = i.match_id "
        f"join (select match_id, team_id, sum(coalesce(runs, 0)) r "
        f"from {A}.fact_player_performances group by 1, 2) b "
        "on b.match_id = i.match_id and b.team_id = i.batting_team_id",
        "b.r + coalesce(i.extras, 0) <> i.total_runs",
        "not i.is_super_over and i.total_runs is not null",
        key="i.innings_id",
        note="penalty runs or missing scorecard rows can cause a small difference",
    ),
    Rule(
        "gold.standings_wins_match_results",
        "gold.fact_tournament_standings",
        "consistency",
        "major",
        "standings wins reconcile with match results, allowing only carried-over matches",
        sql=(
            "select s.tournament_id, count(*) as total, count(*) filter (where "
            "s.wins < coalesce(w.n, 0) or s.wins > coalesce(w.n, 0) + "
            "greatest(s.matches_played - coalesce(l.n, 0), 0)) as failed "
            f"from {A}.fact_tournament_standings s "
            f"left join (select tournament_id, group_name, winner_id, count(*) n "
            f"from {A}.fact_matches where group_name is not null and winner_id is not null "
            "group by 1, 2, 3) w on w.tournament_id = s.tournament_id "
            "and w.group_name = s.group_name and w.winner_id = s.team_id "
            "left join (select tournament_id, group_name, team_id, count(*) n from ("
            f"select tournament_id, group_name, team1_id team_id from {A}.fact_matches "
            f"union all select tournament_id, group_name, team2_id from {A}.fact_matches) u "
            "where group_name is not null group by 1, 2, 3) l on l.tournament_id = s.tournament_id "
            "and l.group_name = s.group_name and l.team_id = s.team_id "
            "group by 1"
        ),
        note=(
            "Super Sixes (2003) and Super Eights (2007) carry earlier-round results into the table, "
            "so derived wins may fall short by at most the matches carried over; any other gap fails"
        ),
    ),
    # ------------------------------------------------------------------ referential integrity
    Rule(
        "gold.deliveries_player_resolved",
        "gold.fact_deliveries",
        "referential_integrity",
        "minor",
        "batter resolved to an ESPN player id (not a Cricsheet-only identity)",
        f"{D} join {M} on m.match_id = d.match_id",
        "d.batter_id like 'cricsheet\\_%'",
        key="d.delivery_id",
        note="share of deliveries whose batter could not be matched safely to a scorecard player",
    ),
    Rule(
        "gold.match_has_innings",
        "gold.fact_matches",
        "referential_integrity",
        "critical",
        "completed non-walkover match has at least two innings rows",
        M,
        f"(select count(*) from {A}.fact_innings i where i.match_id = m.match_id "
        "and not i.is_super_over) < 2",
        "is_completed and not is_walkover",
        key="m.match_id",
    ),
    # ------------------------------------------------------------------ historical coverage
    Rule(
        "gold.ball_by_ball_available",
        "gold.fact_matches",
        "historical_coverage",
        "minor",
        "played match has ball-by-ball data",
        M,
        "not has_ball_by_ball",
        "is_completed and not is_walkover",
        key="m.match_id",
        note="source limitation: not in Cricsheet's World Cup bundle (see ball_by_ball_gap_reason)",
    ),
    Rule(
        "gold.ball_by_ball_gap_explained",
        "gold.fact_matches",
        "historical_coverage",
        "major",
        "every match either has ball-by-ball data or states why not",
        M,
        "not has_ball_by_ball and ball_by_ball_gap_reason is null",
        key="m.match_id",
    ),
    Rule(
        "gold.tournament_has_standings",
        "gold.mart_data_coverage",
        "historical_coverage",
        "major",
        "tournament has a points table",
        f"{A}.mart_data_coverage m",
        "standings_rows = 0",
        key="m.tournament_id",
    ),
    Rule(
        "gold.team_has_squad",
        "gold.mart_data_coverage",
        "historical_coverage",
        "major",
        "every participating team has a squad",
        f"{A}.mart_data_coverage m",
        "teams_with_squad < teams",
        key="m.tournament_id",
    ),
    Rule(
        "gold.tournament_has_player_of_tournament",
        "gold.mart_data_coverage",
        "historical_coverage",
        "minor",
        "tournament names a player of the tournament",
        f"{A}.mart_data_coverage m",
        "not has_player_of_tournament",
        key="m.tournament_id",
    ),
]
