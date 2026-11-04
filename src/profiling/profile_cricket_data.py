"""Cricket-specific profile: entity counts, format/year/stage distributions, coverage."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _df(engine: Engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def entity_counts(engine: Engine) -> dict[str, int]:
    sql = {
        "tournaments": "select count(*) from tournaments",
        "matches": "select count(*) from matches",
        "innings": "select count(*) from innings",
        "deliveries": "select count(*) from deliveries",
        "players": "select count(*) from players",
        "teams": "select count(*) from teams",
        "venues_distinct_text": "select count(distinct venue) from matches",
        "cities_distinct_text": "select count(distinct city) from matches",
        "batting_scorecard_rows": "select count(*) from batting_scorecards",
        "bowling_scorecard_rows": "select count(*) from bowling_scorecards",
        "squad_rows": "select count(*) from squads",
        "standing_rows": "select count(*) from standings",
        "total_runs_in_innings": "select coalesce(sum(total_runs),0) from innings where not is_super_over",
        "total_wickets_in_innings": "select coalesce(sum(wickets),0) from innings where not is_super_over",
    }
    out = {}
    with engine.connect() as conn:
        for key, q in sql.items():
            out[key] = int(conn.execute(text(q)).scalar() or 0)
    return out


def format_distribution(engine: Engine) -> pd.DataFrame:
    return _df(
        engine,
        """select t.format, count(distinct t.tournament_id) tournaments, count(m.match_id) matches,
                  min(m.match_date) first_match, max(m.match_date) last_match
           from tournaments t left join matches m using (tournament_id) group by 1 order by 1""",
    )


def tournament_coverage(engine: Engine) -> pd.DataFrame:
    """One row per tournament: how much of each data type exists."""
    df = _df(
        engine,
        """
        select t.tournament_id, t.format, t.year,
               count(distinct m.match_id) as matches,
               count(distinct m.match_id) filter (where m.result_type = 'RESULT') as completed_matches,
               count(distinct m.match_id) filter (where m.result_type <> 'RESULT') as no_result_or_abandoned,
               count(distinct i.match_id) as matches_with_innings,
               count(distinct b.match_id) as matches_with_batting_scorecard,
               count(distinct bw.match_id) as matches_with_bowling_scorecard,
               count(distinct d.match_id) as matches_with_deliveries,
               count(distinct m.match_id) filter (where m.result_type = 'RESULT' and d.match_id is not null)
                   as completed_with_deliveries,
               count(distinct m.match_id) filter (where m.result_type = 'RESULT' and d.match_id is null)
                   as completed_without_deliveries,
               count(distinct m.venue) as venues
        from tournaments t
        left join matches m on m.tournament_id = t.tournament_id
        left join (select distinct match_id from innings) i on i.match_id = m.match_id
        left join (select distinct match_id from batting_scorecards) b on b.match_id = m.match_id
        left join (select distinct match_id from bowling_scorecards) bw on bw.match_id = m.match_id
        left join (select distinct match_id from deliveries) d on d.match_id = m.match_id
        group by t.tournament_id, t.format, t.year order by t.format, t.year
        """,
    )
    deliveries = _df(
        engine,
        """select m.tournament_id, count(*) deliveries from deliveries d
           join matches m using (match_id) group by 1""",
    )
    df = df.merge(deliveries, on="tournament_id", how="left").fillna({"deliveries": 0})
    df["deliveries"] = df["deliveries"].astype(int)
    df["scorecard_coverage_pct"] = (
        100 * df["matches_with_batting_scorecard"] / df["matches"]
    ).round(1)
    df["ball_by_ball_coverage_pct"] = (100 * df["matches_with_deliveries"] / df["matches"]).round(1)
    df["ball_by_ball_pct_of_completed"] = (
        100
        * df["completed_with_deliveries"]
        / df["completed_matches"].where(df["completed_matches"] > 0)
    ).round(1)
    return df


def stage_distribution(engine: Engine) -> pd.DataFrame:
    return _df(
        engine,
        """select t.format, m.match_stage, count(*) matches
           from matches m join tournaments t using (tournament_id)
           group by 1, 2 order by 1, 3 desc""",
    )


def year_distribution(engine: Engine) -> pd.DataFrame:
    return _df(
        engine,
        """select t.year, t.format, count(*) matches
           from matches m join tournaments t using (tournament_id) group by 1, 2 order by 1, 2""",
    )


def result_distribution(engine: Engine) -> pd.DataFrame:
    return _df(
        engine,
        "select result_type, match_status, scorecard_status, ball_by_ball_status, count(*) matches "
        "from matches group by 1, 2, 3, 4 order by 5 desc",
    )


def venue_variants(engine: Engine) -> pd.DataFrame:
    """Venue strings that differ only by case/punctuation/whitespace (candidate duplicates)."""
    df = _df(
        engine,
        "select venue, city, count(*) matches from matches where venue is not null group by 1, 2",
    )
    df["venue_key"] = (
        df["venue"]
        .str.lower()
        .str.replace(r"[^a-z0-9 ]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    grouped = df.groupby("venue_key").agg(
        variants=("venue", "nunique"), names=("venue", lambda s: " | ".join(sorted(set(s))))
    )
    return grouped[grouped["variants"] > 1].reset_index()


def profile_cricket(engine: Engine) -> dict[str, Any]:
    return {
        "entity_counts": entity_counts(engine),
        "format_distribution": format_distribution(engine),
        "tournament_coverage": tournament_coverage(engine),
        "stage_distribution": stage_distribution(engine),
        "year_distribution": year_distribution(engine),
        "result_distribution": result_distribution(engine),
        "venue_variants": venue_variants(engine),
    }
