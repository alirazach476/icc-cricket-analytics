"""Tournament-level rules."""

from __future__ import annotations

from src.validation.rules import Rule

T = "tournaments t"
TID = "t.tournament_id"

RULES: list[Rule] = [
    Rule(
        "tournaments.core_fields_present",
        "tournaments",
        "completeness",
        "major",
        "host, dates, winner, runner-up and team count are all recorded",
        T,
        "t.host_country is null or t.start_date is null or t.end_date is null or t.winner is null "
        "or t.runner_up is null or t.number_of_teams is null",
        tid=TID,
        key=TID,
    ),
    Rule(
        "tournaments.number_of_matches_present",
        "tournaments",
        "completeness",
        "minor",
        "verified match count is stored on the tournament",
        T,
        "t.number_of_matches is null",
        tid=TID,
        key=TID,
    ),
    Rule(
        "tournaments.dates_ordered",
        "tournaments",
        "validity",
        "major",
        "start date is not after end date",
        T,
        "t.start_date > t.end_date",
        tid=TID,
        key=TID,
    ),
    Rule(
        "tournaments.team_count_matches_data",
        "tournaments",
        "consistency",
        "major",
        "number_of_teams equals the distinct teams that appear as team1/team2 in matches",
        T,
        "t.number_of_teams <> (select count(*) from (select team1_id x from matches "
        "where tournament_id = t.tournament_id union select team2_id from matches "
        "where tournament_id = t.tournament_id) q)",
        tid=TID,
        key=TID,
    ),
    Rule(
        "tournaments.winner_won_the_final",
        "tournaments",
        "consistency",
        "major",
        "the recorded winner is the winner of the Final match",
        T,
        "not exists (select 1 from matches m join teams w on w.team_id = m.winner_id "
        "where m.tournament_id = t.tournament_id and m.match_stage = 'Final' and w.team_name = t.winner)",
        tid=TID,
        key=TID,
    ),
]
