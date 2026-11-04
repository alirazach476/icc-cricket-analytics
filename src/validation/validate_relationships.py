"""Relationship, historical-coverage, standings and squad rules."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from src.validation.rules import GLOBAL, Rule

M = "matches m"
PLAYED = "m.result_type = 'RESULT' and coalesce(m.result_margin, '') not ilike '%walkover%'"
GROUPS = (
    "(select tournament_id, group_name, sum(wins) w, sum(losses) l, count(*) n, "
    "max(position) mx, count(distinct position) dp from standings group by 1, 2) g"
)
SQUAD_AGG = (
    "(select tournament_id, team_id, "
    "sum(case when is_captain and not is_withdrawn then 1 else 0 end) captains, "
    "sum(case when not is_withdrawn then 1 else 0 end) active from squads group by 1, 2) q"
)
TOURNAMENT_TEAMS = (
    "(select distinct tournament_id, team_id from (select tournament_id, team1_id team_id from matches "
    "union select tournament_id, team2_id from matches) u) r"
)

RULES: list[Rule] = [
    # ---- historical coverage: how much of the data that should exist does exist
    Rule(
        "coverage.played_matches_have_scorecard",
        "coverage",
        "historical_coverage",
        "major",
        "played matches have a batting scorecard",
        M,
        "not exists (select 1 from batting_scorecards b where b.match_id = m.match_id)",
        where=PLAYED,
        key="m.match_id",
    ),
    Rule(
        "coverage.played_matches_have_ball_by_ball",
        "coverage",
        "historical_coverage",
        "major",
        "played matches have ball-by-ball deliveries",
        M,
        "not exists (select 1 from deliveries d where d.match_id = m.match_id)",
        where=PLAYED,
        key="m.match_id",
        note="data is unavailable at every free source for T20 2007-2012, so this is a coverage gap, not a defect",
    ),
    Rule(
        "coverage.tournament_has_standings",
        "coverage",
        "historical_coverage",
        "major",
        "tournament has points-table rows",
        "tournaments t",
        "not exists (select 1 from standings s where s.tournament_id = t.tournament_id)",
        tid="t.tournament_id",
        key="t.tournament_id",
    ),
    Rule(
        "coverage.tournament_has_squads",
        "coverage",
        "historical_coverage",
        "major",
        "tournament has squad rows",
        "tournaments t",
        "not exists (select 1 from squads s where s.tournament_id = t.tournament_id)",
        tid="t.tournament_id",
        key="t.tournament_id",
    ),
    Rule(
        "coverage.each_team_has_squad",
        "coverage",
        "historical_coverage",
        "major",
        "every team that played has a squad for that tournament",
        TOURNAMENT_TEAMS,
        "not exists (select 1 from squads s where s.tournament_id = r.tournament_id and s.team_id = r.team_id)",
        tid="r.tournament_id",
        key="r.team_id",
    ),
    Rule(
        "coverage.tournament_has_awards",
        "coverage",
        "historical_coverage",
        "minor",
        "tournament has award rows (player of the tournament etc.)",
        "tournaments t",
        "not exists (select 1 from tournament_awards a where a.tournament_id = t.tournament_id)",
        tid="t.tournament_id",
        key="t.tournament_id",
        note="tournament_awards has never been populated",
    ),
    # ---- standings
    Rule(
        "standings.played_equals_results",
        "standings",
        "consistency",
        "major",
        "matches played = wins + losses + ties + no results",
        "standings s",
        "s.matches_played <> coalesce(s.wins, 0) + coalesce(s.losses, 0) + coalesce(s.ties, 0) "
        "+ coalesce(s.no_results, 0)",
        tid="s.tournament_id",
        key="s.standing_id",
        note="a tie settled by super over is credited as a win by the source",
    ),
    Rule(
        "standings.group_wins_equal_losses",
        "standings",
        "consistency",
        "major",
        "within a group, total wins = total losses",
        GROUPS,
        "g.w <> g.l",
        tid="g.tournament_id",
        key="g.group_name",
    ),
    Rule(
        "standings.positions_contiguous",
        "standings",
        "validity",
        "minor",
        "positions in a group are 1..n without gaps or repeats",
        GROUPS,
        "g.mx <> g.n or g.dp <> g.n",
        tid="g.tournament_id",
        key="g.group_name",
    ),
    Rule(
        "standings.team_played_in_tournament",
        "standings",
        "referential_integrity",
        "major",
        "a standings team actually played matches in that tournament",
        "standings s",
        "not exists (select 1 from matches m where m.tournament_id = s.tournament_id "
        "and s.team_id in (m.team1_id, m.team2_id))",
        tid="s.tournament_id",
        key="s.standing_id",
    ),
    Rule(
        "standings.qualified_flag_present",
        "standings",
        "completeness",
        "minor",
        "qualified flag is derived for every row",
        "standings s",
        "s.qualified is null",
        tid="s.tournament_id",
        key="s.standing_id",
    ),
    # ---- squads
    Rule(
        "squads.one_captain",
        "squads",
        "consistency",
        "major",
        "an active squad has exactly one captain",
        SQUAD_AGG,
        "q.captains <> 1",
        tid="q.tournament_id",
        key="q.team_id",
    ),
    Rule(
        "squads.at_least_eleven_active",
        "squads",
        "validity",
        "major",
        "an active squad has at least 11 players",
        SQUAD_AGG,
        "q.active < 11",
        tid="q.tournament_id",
        key="q.team_id",
    ),
]


def declared_fk_rules(engine: Engine) -> list[Rule]:
    """One referential-integrity rule per foreign key declared in the live schema."""
    insp = inspect(engine)
    rules: list[Rule] = []
    for table in sorted(insp.get_table_names()):
        for fk in insp.get_foreign_keys(table):
            parent = fk["referred_table"]
            for col, pcol in zip(fk["constrained_columns"], fk["referred_columns"], strict=True):
                sql = (
                    f"select '{GLOBAL}' as tournament_id, count(*) as total, "
                    f'count(*) filter (where p."{pcol}" is null) as failed '
                    f'from "{table}" c left join "{parent}" p on c."{col}" = p."{pcol}" '
                    f'where c."{col}" is not null'
                )
                rules.append(
                    Rule(
                        f"fk.{table}.{col}",
                        "relationships",
                        "referential_integrity",
                        "critical",
                        f"{table}.{col} references an existing {parent}.{pcol}",
                        sql=sql,
                    )
                )
    return rules
