"""Innings-level rules, including scorecard and ball-by-ball reconciliation."""

from __future__ import annotations

from src.validation.rules import Rule

BASE = (
    "innings i join matches m on m.match_id = i.match_id "
    "join tournaments t on t.tournament_id = m.tournament_id"
)
WITH_BALLS = (
    BASE + " join (select innings_id, count(*) n, max(delivery_sequence) mx, sum(total_runs) runs, "
    "sum(case when is_wicket then 1 else 0 end) w, "
    "sum(case when not coalesce(is_wide, false) and not coalesce(is_no_ball, false) then 1 else 0 end) fair "
    "from deliveries group by innings_id) a on a.innings_id = i.innings_id"
)
WITH_BAT = (
    BASE
    + " join (select match_id, innings_number, sum(coalesce(runs, 0)) r from batting_scorecards "
    "group by 1, 2) b on b.match_id = i.match_id and b.innings_number = i.innings_number"
)
KEY = "i.innings_id"
NOT_SUPER = "not i.is_super_over"
CHASE = "i.innings_number = 2 and not i.is_super_over"
FIRST = "(select o.{col} from innings o where o.match_id = i.match_id and o.innings_number = 1)"

RULES: list[Rule] = [
    Rule(
        "innings.unique_per_match",
        "innings",
        "uniqueness",
        "critical",
        "(match, innings_number) occurs once",
        BASE,
        "(select count(*) from innings o where o.match_id = i.match_id "
        "and o.innings_number = i.innings_number) > 1",
        key=KEY,
    ),
    Rule(
        "innings.overs_present",
        "innings",
        "completeness",
        "major",
        "overs are recorded",
        BASE,
        "i.overs is null",
        key=KEY,
    ),
    Rule(
        "innings.second_innings_has_target",
        "innings",
        "completeness",
        "minor",
        "a chasing innings stores its target",
        BASE,
        "i.target is null",
        where=CHASE,
        key=KEY,
    ),
    Rule(
        "innings.wickets_in_range",
        "innings",
        "validity",
        "critical",
        "wickets are between 0 and 10",
        BASE,
        "i.wickets is null or i.wickets < 0 or i.wickets > 10",
        key=KEY,
    ),
    Rule(
        "innings.runs_non_negative",
        "innings",
        "validity",
        "critical",
        "total runs are present and not negative",
        BASE,
        "i.total_runs is null or i.total_runs < 0",
        key=KEY,
        note="failures are super-over innings whose totals were never stored (derivable from deliveries)",
    ),
    Rule(
        "innings.overs_within_format_limit",
        "innings",
        "validity",
        "major",
        "overs do not exceed 50 (ODI) or 20 (T20)",
        BASE,
        "i.overs > case when t.format = 'ODI' then 50 else 20 end",
        where=NOT_SUPER,
        key=KEY,
    ),
    Rule(
        "innings.teams_differ",
        "innings",
        "validity",
        "critical",
        "batting and bowling team are different",
        BASE,
        "i.batting_team_id = i.bowling_team_id",
        key=KEY,
    ),
    Rule(
        "innings.legal_balls_within_limit",
        "innings",
        "validity",
        "major",
        "legal deliveries (excluding wides and no-balls) do not exceed 300 (ODI) or 120 (T20)",
        WITH_BALLS,
        "a.fair > case when t.format = 'ODI' then 300 else 120 end",
        where=NOT_SUPER,
        key=KEY,
    ),
    Rule(
        "innings.teams_are_match_participants",
        "innings",
        "referential_integrity",
        "critical",
        "batting and bowling team are the two teams of the match",
        BASE,
        "i.batting_team_id not in (m.team1_id, m.team2_id) or i.bowling_team_id not in (m.team1_id, m.team2_id)",
        key=KEY,
    ),
    Rule(
        "innings.total_matches_batting_scorecard",
        "innings",
        "consistency",
        "critical",
        "total = sum of batting-scorecard runs + extras",
        WITH_BAT,
        "b.r + coalesce(i.extras, 0) <> i.total_runs",
        key=KEY,
    ),
    Rule(
        "innings.total_matches_deliveries",
        "innings",
        "consistency",
        "critical",
        "total = sum of delivery runs (matches with ball-by-ball)",
        WITH_BALLS,
        "a.runs <> i.total_runs",
        key=KEY,
    ),
    Rule(
        "innings.wickets_match_deliveries",
        "innings",
        "consistency",
        "major",
        "wickets = number of wicket deliveries (matches with ball-by-ball)",
        WITH_BALLS,
        "a.w <> i.wickets",
        key=KEY,
        note="retired-out and similar dismissals may legitimately differ",
    ),
    Rule(
        "innings.delivery_sequence_contiguous",
        "innings",
        "consistency",
        "major",
        "delivery_sequence runs 1..n with no gaps",
        WITH_BALLS,
        "a.mx <> a.n",
        key=KEY,
    ),
    Rule(
        "innings.chasing_team_follows_first",
        "innings",
        "consistency",
        "major",
        "the chasing team is the team that bowled first",
        BASE,
        "i.batting_team_id <> " + FIRST.format(col="bowling_team_id"),
        where=CHASE,
        key=KEY,
    ),
    Rule(
        "innings.target_matches_first_innings",
        "innings",
        "consistency",
        "minor",
        "target = first-innings total + 1",
        BASE,
        "i.target <> " + FIRST.format(col="total_runs") + " + 1",
        where=CHASE + " and i.target is not null",
        key=KEY,
        note="rain-adjusted (DLS) targets legitimately differ; no DLS flag exists in the data",
    ),
]
