"""Player rules, scoped to the players who actually took part in each tournament."""

from __future__ import annotations

from src.validation.rules import Rule

PARTICIPANTS = (
    "(select m.tournament_id, b.player_id from batting_scorecards b join matches m on m.match_id = b.match_id "
    "union select m.tournament_id, bw.player_id from bowling_scorecards bw join matches m on m.match_id = bw.match_id "
    "union select m.tournament_id, d.batter_id from deliveries d join matches m on m.match_id = d.match_id "
    "union select m.tournament_id, d.bowler_id from deliveries d join matches m on m.match_id = d.match_id) p "
    "join players pl on pl.player_id = p.player_id"
)
NAMES = (
    " join (select lower(trim(full_name)) k, count(distinct player_id) n from players group by 1) nm "
    "on nm.k = lower(trim(pl.full_name))"
)
TID = "p.tournament_id"
KEY = "pl.player_id"

RULES: list[Rule] = [
    Rule(
        "players.single_identity",
        "players",
        "uniqueness",
        "critical",
        "no other player id shares this player's name (ESPN vs Cricsheet ids)",
        PARTICIPANTS + NAMES,
        "nm.n > 1",
        tid=TID,
        key=KEY,
        note="exact-name matches only; initial-vs-full-name variants are not detected here",
    ),
    Rule(
        "players.name_present",
        "players",
        "completeness",
        "critical",
        "full name is recorded",
        PARTICIPANTS,
        "pl.full_name is null or trim(pl.full_name) = ''",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "players.source_id_present",
        "players",
        "completeness",
        "major",
        "source player id is recorded",
        PARTICIPANTS,
        "pl.source_player_id is null",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "players.birth_date_present",
        "players",
        "completeness",
        "minor",
        "date of birth is recorded",
        PARTICIPANTS,
        "pl.date_of_birth is null",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "players.styles_present",
        "players",
        "completeness",
        "minor",
        "batting and bowling style are recorded",
        PARTICIPANTS,
        "pl.batting_style is null or pl.bowling_style is null",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "players.birth_date_plausible",
        "players",
        "validity",
        "major",
        "date of birth is between 1940 and 2012",
        PARTICIPANTS,
        "pl.date_of_birth < date '1940-01-01' or pl.date_of_birth > date '2012-12-31'",
        where="pl.date_of_birth is not null",
        tid=TID,
        key=KEY,
    ),
    Rule(
        "players.batter_in_tournament_squad",
        "players",
        "consistency",
        "minor",
        "a batting-scorecard player is in his team's squad for that tournament",
        "batting_scorecards b join matches m on m.match_id = b.match_id "
        "left join squads s on s.tournament_id = m.tournament_id and s.team_id = b.team_id "
        "and s.player_id = b.player_id",
        "s.squad_id is null",
        key="b.batting_scorecard_id",
        note="squad lists can omit late replacements",
    ),
]
