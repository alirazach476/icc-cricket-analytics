"""Relationship, identity and cross-store consistency profiling (read-only SQL)."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _scalar(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        value = conn.execute(text(sql)).scalar()
    return int(value or 0)


def _row(
    relationship: str,
    kind: str,
    parent: str,
    child: str,
    checked: int,
    violations: int,
    *,
    severity_if_bad: str = "fail",
    detail: str = "",
) -> dict[str, Any]:
    return {
        "relationship": relationship,
        "type": kind,
        "parent": parent,
        "child": child,
        "checked_rows": checked,
        "violating_rows": violations,
        "status": "ok" if violations == 0 else severity_if_bad,
        "detail": detail,
    }


def declared_foreign_keys(engine: Engine) -> list[dict[str, Any]]:
    """Orphan check for every foreign key declared in the database."""
    insp = inspect(engine)
    rows: list[dict[str, Any]] = []
    for table in sorted(insp.get_table_names()):
        for fk in insp.get_foreign_keys(table):
            parent = fk["referred_table"]
            for col, pcol in zip(fk["constrained_columns"], fk["referred_columns"], strict=True):
                checked = _scalar(
                    engine, f'select count(*) from "{table}" where "{col}" is not null'
                )
                bad = _scalar(
                    engine,
                    f'select count(*) from "{table}" c left join "{parent}" p on c."{col}" = p."{pcol}" '
                    f'where c."{col}" is not null and p."{pcol}" is null',
                )
                rows.append(
                    _row(
                        f"{table}.{col} -> {parent}.{pcol}",
                        "declared FK",
                        parent,
                        table,
                        checked,
                        bad,
                    )
                )
    return rows


# (relationship, parent, child, checked_sql, violating_sql, severity if violated, detail)
LOGICAL_CHECKS: list[tuple[str, str, str, str, str, str, str]] = [
    (
        "every match has innings",
        "matches",
        "innings",
        "select count(*) from matches",
        "select count(*) from matches m where not exists (select 1 from innings i where i.match_id = m.match_id)",
        "info",
        "abandoned, no-result and walkover matches legitimately have none; real errors are caught by the RESULT check",
    ),
    (
        "RESULT matches without innings (excluding walkovers)",
        "matches",
        "innings",
        "select count(*) from matches where result_type = 'RESULT'",
        "select count(*) from matches m where result_type = 'RESULT' and coalesce(result_margin,'') not ilike '%walkover%' "
        "and not exists (select 1 from innings i where i.match_id = m.match_id)",
        "fail",
        "a played match must have innings; walkovers (no ball bowled) are excluded",
    ),
    (
        "walkover matches (no ball bowled)",
        "matches",
        "innings",
        "select count(*) from matches where result_type = 'RESULT'",
        "select count(*) from matches where result_type = 'RESULT' and coalesce(result_margin,'') ilike '%walkover%'",
        "info",
        "legitimate: result awarded without play; excluded from batting/ball-by-ball analyses",
    ),
    (
        "every match has batting scorecards",
        "matches",
        "batting_scorecards",
        "select count(*) from matches",
        "select count(*) from matches m where not exists (select 1 from batting_scorecards b where b.match_id = m.match_id)",
        "info",
        "",
    ),
    (
        "ball_by_ball_status=complete has deliveries",
        "matches",
        "deliveries",
        "select count(*) from matches where ball_by_ball_status = 'complete'",
        "select count(*) from matches m where ball_by_ball_status = 'complete' and not exists "
        "(select 1 from deliveries d where d.match_id = m.match_id)",
        "fail",
        "",
    ),
    (
        "deliveries exist only for status=complete",
        "matches",
        "deliveries",
        "select count(distinct match_id) from deliveries",
        "select count(*) from (select distinct match_id from deliveries) d join matches m using (match_id) "
        "where m.ball_by_ball_status <> 'complete'",
        "fail",
        "",
    ),
    (
        "innings batting/bowling team plays in the match",
        "match_teams",
        "innings",
        "select count(*) from innings",
        "select count(*) from innings i join matches m using (match_id) "
        "where i.batting_team_id not in (m.team1_id, m.team2_id) or i.bowling_team_id not in (m.team1_id, m.team2_id)",
        "fail",
        "",
    ),
    (
        "match winner is one of the two teams",
        "matches",
        "matches",
        "select count(*) from matches where winner_id is not null",
        "select count(*) from matches where winner_id is not null and winner_id not in (team1_id, team2_id)",
        "fail",
        "",
    ),
    (
        "toss winner is one of the two teams",
        "matches",
        "matches",
        "select count(*) from matches where toss_winner_id is not null",
        "select count(*) from matches where toss_winner_id is not null and toss_winner_id not in (team1_id, team2_id)",
        "fail",
        "",
    ),
    (
        "tie-break winner is recorded in winner_id",
        "matches",
        "matches",
        "select count(*) from matches where result_type = 'RESULT' and winner_id is null",
        "select count(*) from matches where result_type = 'RESULT' and winner_id is null and result_margin ilike '%won%'",
        "warn",
        "tied matches decided by super over / boundary count / eliminator name a winner only in result_margin text",
    ),
    (
        "RESULT matches without a winner (ties)",
        "matches",
        "matches",
        "select count(*) from matches where result_type = 'RESULT'",
        "select count(*) from matches where result_type = 'RESULT' and winner_id is null",
        "info",
        "genuine ties; target definition for win/loss models must handle them explicitly",
    ),
    (
        "match date inside tournament window",
        "tournaments",
        "matches",
        "select count(*) from matches",
        "select count(*) from matches m join tournaments t using (tournament_id) "
        "where m.match_date < t.start_date or m.match_date > t.end_date",
        "fail",
        "",
    ),
    (
        "batting scorecard team plays in the match",
        "match_teams",
        "batting_scorecards",
        "select count(*) from batting_scorecards where team_id is not null",
        "select count(*) from batting_scorecards b join matches m using (match_id) "
        "where b.team_id is not null and b.team_id not in (m.team1_id, m.team2_id)",
        "fail",
        "",
    ),
    (
        "innings total = batting runs + extras",
        "innings",
        "batting_scorecards",
        "select count(*) from innings i join (select match_id, innings_number from batting_scorecards "
        "group by 1,2) b using (match_id, innings_number)",
        "select count(*) from innings i join (select match_id, innings_number, sum(coalesce(runs,0)) r "
        "from batting_scorecards group by 1,2) b using (match_id, innings_number) "
        "where b.r + coalesce(i.extras,0) <> i.total_runs",
        "fail",
        "scorecard reconciliation",
    ),
    (
        "innings total = sum of delivery runs",
        "innings",
        "deliveries",
        "select count(*) from innings i join (select innings_id from deliveries group by 1) d using (innings_id)",
        "select count(*) from innings i join (select innings_id, sum(total_runs) r from deliveries group by 1) d "
        "using (innings_id) where d.r <> i.total_runs",
        "fail",
        "ball-by-ball reconciliation",
    ),
    (
        "deliveries: legal ball numbering has no gaps per innings",
        "innings",
        "deliveries",
        "select count(*) from (select innings_id from deliveries group by 1) x",
        "select count(*) from (select innings_id, max(legal_ball_number) mx, count(distinct legal_ball_number) n "
        "from deliveries where legal_ball_number is not null group by 1) y where y.mx <> y.n",
        "warn",
        "",
    ),
    (
        "standings teams played in that tournament",
        "matches",
        "standings",
        "select count(*) from standings",
        "select count(*) from standings s where not exists (select 1 from matches m where m.tournament_id = s.tournament_id "
        "and s.team_id in (m.team1_id, m.team2_id))",
        "warn",
        "",
    ),
    (
        "squad teams played in that tournament",
        "matches",
        "squads",
        "select count(*) from squads",
        "select count(*) from squads s where not exists (select 1 from matches m where m.tournament_id = s.tournament_id "
        "and s.team_id in (m.team1_id, m.team2_id))",
        "warn",
        "",
    ),
]


SAMPLE_SQL: dict[str, str] = {
    "match winner is one of the two teams": "select match_id, tournament_id, team1_id, team2_id, winner_id, result_margin from matches "
    "where winner_id is not null and winner_id not in (team1_id, team2_id) order by match_id limit 8",
    "toss winner is one of the two teams": "select match_id, tournament_id, team1_id, team2_id, toss_winner_id from matches "
    "where toss_winner_id is not null and toss_winner_id not in (team1_id, team2_id) order by match_id limit 8",
    "RESULT matches without innings (excluding walkovers)": "select match_id, tournament_id, result_margin from matches m where result_type = 'RESULT' "
    "and coalesce(result_margin,'') not ilike '%walkover%' and not exists "
    "(select 1 from innings i where i.match_id = m.match_id) limit 8",
    "tie-break winner is recorded in winner_id": "select match_id, tournament_id, result_margin from matches where result_type = 'RESULT' "
    "and winner_id is null and result_margin ilike '%won%' order by match_id limit 8",
    "match date inside tournament window": "select m.match_id, m.tournament_id, m.match_date from matches m join tournaments t using (tournament_id) "
    "where m.match_date < t.start_date or m.match_date > t.end_date limit 8",
    "innings total = sum of delivery runs": "select i.innings_id, i.total_runs, d.r from innings i join (select innings_id, sum(total_runs) r from deliveries "
    "group by 1) d using (innings_id) where d.r <> i.total_runs limit 8",
    "innings total = batting runs + extras": "select i.innings_id, i.total_runs, b.r, i.extras from innings i join (select match_id, innings_number, "
    "sum(coalesce(runs,0)) r from batting_scorecards group by 1,2) b using (match_id, innings_number) "
    "where b.r + coalesce(i.extras,0) <> i.total_runs limit 8",
}


def _examples(engine: Engine, rel: str) -> str:
    sql = SAMPLE_SQL.get(rel)
    if not sql:
        return ""
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return "; ".join("(" + ", ".join(str(v) for v in r) + ")" for r in rows)


def logical_relationships(engine: Engine) -> list[dict[str, Any]]:
    rows = []
    for rel, parent, child, checked_sql, bad_sql, severity, detail in LOGICAL_CHECKS:
        try:
            row = _row(
                rel,
                "logical",
                parent,
                child,
                _scalar(engine, checked_sql),
                _scalar(engine, bad_sql),
                severity_if_bad=severity,
                detail=detail,
            )
            row["examples"] = _examples(engine, rel) if row["violating_rows"] else ""
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - report, never abort the audit
            rows.append(
                {
                    "relationship": rel,
                    "type": "logical",
                    "parent": parent,
                    "child": child,
                    "checked_rows": 0,
                    "violating_rows": 0,
                    "status": "error",
                    "detail": f"{type(exc).__name__}: {str(exc)[:120]}",
                }
            )
    return rows


def identity_checks(engine: Engine) -> dict[str, Any]:
    """Player and team identity consistency."""
    with engine.connect() as conn:
        players = pd.read_sql(text("select player_id, full_name, source_name from players"), conn)
        teams = pd.read_sql(text("select team_id, team_name, short_name from teams"), conn)
        used_teams = {
            r[0]
            for r in conn.execute(
                text("select team1_id from matches union select team2_id from matches")
            )
        }
        bbb_players = {
            r[0] for r in conn.execute(text("select distinct batter_id from deliveries"))
        }
        sc_players = {
            r[0] for r in conn.execute(text("select distinct player_id from batting_scorecards"))
        }

    placeholder_ids = teams.loc[teams["team_name"] == teams["team_id"], "team_id"].tolist()
    placeholder_refs = 0
    if placeholder_ids:
        in_list = ", ".join(f"'{t}'" for t in placeholder_ids)
        placeholder_refs = _scalar(
            engine,
            f"select count(*) from matches where winner_id in ({in_list}) or toss_winner_id in ({in_list})",
        )
    players["prefix"] = players["player_id"].str.split("_").str[0]
    players["name_key"] = players["full_name"].str.lower().str.strip()
    by_name = players.groupby("name_key")["player_id"].nunique()
    cross = players.groupby("name_key")["prefix"].nunique()
    dup_names = by_name[by_name > 1]
    exact_cross_source = int(((by_name > 1) & (cross > 1)).sum())

    bbb_only = {p for p in bbb_players if str(p).startswith("cricsheet_")}
    return {
        "players_total": int(len(players)),
        "players_by_source": players["prefix"].value_counts().to_dict(),
        "names_with_multiple_ids": int(len(dup_names)),
        "names_split_across_sources": exact_cross_source,
        "delivery_batters_with_cricsheet_id": len(bbb_only),
        "scorecard_batters_distinct": len(sc_players),
        "delivery_and_scorecard_player_id_overlap": len(bbb_players & sc_players),
        "teams_total": int(len(teams)),
        "teams_named_as_their_id": teams.loc[
            teams["team_name"] == teams["team_id"], "team_id"
        ].tolist(),
        "teams_unused_in_matches": sorted(set(teams["team_id"]) - used_teams),
        "placeholder_team_references": placeholder_refs,
        "teams_missing_short_name": int(teams["short_name"].isna().sum()),
        "short_names_not_uppercase_abbrev": sorted(
            teams.loc[teams["short_name"].fillna("").str.len() > 3, "short_name"].tolist()
        ),
    }


def warehouse_consistency(engine: Engine, duckdb_path: str) -> list[dict[str, Any]]:
    """Compare row counts in Postgres with the DuckDB warehouse (detects stale syncs)."""
    import duckdb

    rows: list[dict[str, Any]] = []
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "relationship": "warehouse available",
                "type": "consistency",
                "parent": "postgres",
                "child": "duckdb",
                "checked_rows": 0,
                "violating_rows": 1,
                "status": "error",
                "detail": str(exc)[:150],
            }
        ]
    insp = inspect(engine)
    duck_tables = {
        r[0]
        for r in con.execute(
            "select table_name from information_schema.tables where table_schema='main'"
        ).fetchall()
    }
    for table in sorted(insp.get_table_names()):
        if table in {"alembic_version"} or table not in duck_tables:
            continue
        pg = _scalar(engine, f'select count(*) from "{table}"')
        dk = int(con.execute(f'select count(*) from main."{table}"').fetchone()[0])
        rows.append(
            _row(
                f"row count {table}",
                "consistency",
                f"postgres={pg}",
                f"duckdb={dk}",
                pg,
                abs(pg - dk),
                severity_if_bad="warn",
                detail="warehouse out of date" if pg != dk else "",
            )
        )
    con.close()
    return rows
