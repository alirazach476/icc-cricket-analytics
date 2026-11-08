"""Ball-by-ball coverage after adding the Cricsheet all-T20I archive matches (World Twenty20 2007-2012)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils import database  # noqa: E402


@pytest.fixture(autouse=True)
def _wc() -> None:
    database.set_competition("wc")


def _one(sql: str):
    return database.run(sql).iloc[0, 0]


def test_most_played_world_cup_matches_have_ball_by_ball() -> None:
    played = int(_one("select count(*) from gold.fact_matches where is_completed and result_type='RESULT'"))
    with_bbb = int(_one("select count(*) from gold.fact_matches where has_ball_by_ball and is_completed and result_type='RESULT'"))
    assert with_bbb / played > 0.84  # 75% before the World Twenty20 2007-2012 matches were added; 1999 has no ball-by-ball source


def test_world_twenty20_2007_to_2012_are_now_covered() -> None:
    d = database.run(
        "select tournament_name, count(*) filter (where has_ball_by_ball) w, count(*) filter (where is_completed and result_type='RESULT') p "
        "from gold.fact_matches where tournament_name like 'ICC World Twenty20 20%' group by 1"
    )
    for r in d.itertuples():
        if r.tournament_name.endswith(("2007", "2009")):
            assert r.w == r.p, r  # every match of these two editions has ball-by-ball now


def test_added_matches_reconcile_with_their_scorecards() -> None:
    import csv
    from pathlib import Path

    known = {r["match_id"] for r in csv.DictReader((Path(__file__).resolve().parents[1] / "config" / "bbb_known_shortfalls.csv").open(encoding="utf-8"))}
    assert known == {"1415729", "1415743", "1415753"}  # disclosed 1-run source shortfalls, nothing else is allowed to differ
    bad = database.run(
        "select count(*) from gold.fact_innings i join (select innings_id, sum(total_runs) s from gold.fact_deliveries group by 1) t using(innings_id) "
        "where not i.is_super_over and i.total_runs <> t.s and coalesce(i.penalties, 0) = 0 "
        f"and i.match_id not in ({','.join(repr(k) for k in sorted(known))})"
    ).iloc[0, 0]
    assert int(bad) == 0


def test_every_match_without_ball_by_ball_says_why() -> None:
    n = database.run("select count(*) from gold.fact_matches where not has_ball_by_ball and ball_by_ball_gap_reason is null").iloc[0, 0]
    assert int(n) == 0
