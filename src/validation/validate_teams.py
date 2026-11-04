"""Team rules, scoped to teams referenced by each tournament's matches."""

from __future__ import annotations

from src.validation.rules import Rule

REFERENCED = (
    "(select tournament_id, team_id from ("
    "select tournament_id, team1_id team_id from matches "
    "union select tournament_id, team2_id from matches "
    "union select tournament_id, winner_id from matches where winner_id is not null "
    "union select tournament_id, toss_winner_id from matches where toss_winner_id is not null) u) r "
    "left join teams tm on tm.team_id = r.team_id"
)
TID = "r.tournament_id"
KEY = "r.team_id"

RULES: list[Rule] = [
    Rule(
        "teams.referenced_team_has_real_name",
        "teams",
        "completeness",
        "major",
        "every team referenced by a match exists and has a real name (not its id)",
        REFERENCED,
        "tm.team_id is null or tm.team_name = tm.team_id",
        tid=TID,
        key=KEY,
        note="alias ids such as espn_32 / espn_34 (Nepal / Uganda) fail here",
    ),
    Rule(
        "teams.short_name_present",
        "teams",
        "completeness",
        "minor",
        "short name is recorded",
        REFERENCED,
        "tm.short_name is null",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "teams.country_code_present",
        "teams",
        "completeness",
        "minor",
        "country code is recorded",
        REFERENCED,
        "tm.country_code is null",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "teams.short_name_format",
        "teams",
        "consistency",
        "minor",
        "short name is an upper-case abbreviation of at most 4 characters",
        REFERENCED,
        "length(tm.short_name) > 4 or tm.short_name <> upper(tm.short_name)",
        where="tm.short_name is not null",
        tid=TID,
        key=KEY,
    ),
]
