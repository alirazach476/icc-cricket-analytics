"""Match centre data: flags, scoreboard and scorecards agree with the stored data."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils import database  # noqa: E402
from app.utils import match_centre as MC  # noqa: E402
from app.utils.flags import canonical, flag_code, flag_map  # noqa: E402

FLAG_DIR = Path(__file__).resolve().parents[1] / "web" / "public" / "flags"


def _teams() -> set[str]:
    names: set[str] = set()
    for c in ("wc", "ct", "wtc"):
        database.set_competition(c)
        names |= set(database.run("select team_name t from gold.dim_teams")["t"])
    database.set_competition("wc")
    return names


def test_every_national_team_has_a_flag_file() -> None:
    for t in _teams():
        code = flag_code(t)
        if t == "West Indies":  # a multi-nation board has no national flag: neutral badge, never a wrong flag
            assert code is None
        else:
            assert code and (FLAG_DIR / f"{code}.svg").exists(), t


def test_flag_aliases() -> None:
    assert canonical("USA") == canonical("United States") == "United States of America"
    assert canonical("UAE") == "United Arab Emirates"
    assert flag_code("England") == "gb-eng" and flag_code("Scotland") == "gb-sct"
    assert flag_code("nonsense team") is None
    assert "usa" in flag_map()


def test_scoreboard_matches_stored_innings() -> None:
    database.set_competition("wc")
    mid = database.run(
        "select match_id from gold.fact_matches where has_ball_by_ball and format='T20' and result_type='RESULT' "
        "and margin_type='runs' order by match_date desc limit 1"
    ).iloc[0, 0]
    p = MC.payload(mid)
    stored = database.run(
        "select innings_number n, total_runs r, wickets w from gold.fact_innings where match_id=? order by 1", (mid,)
    )
    assert [(i["n"], i["runs"], i["wickets"]) for i in p["innings"]] == list(
        stored.itertuples(index=False, name=None)
    )
    assert "WON BY" in p["result"] and sum(t["winner"] for t in p["teams"]) == 1
    # batting scorecard runs + extras = innings total
    for i in p["innings"]:
        assert sum(b["runs"] or 0 for b in i["batting"]) + (i["extras"]["total"] or 0) == i["runs"]
        assert len(i["fow"]) == i["wickets"] or i["wickets"] == 10
    assert MC.charts(mid, p)


def test_abandoned_and_test_matches() -> None:
    database.set_competition("ct")
    mid = database.run("select match_id from gold.fact_matches where margin_type='abandoned' limit 1").iloc[0, 0]
    p = MC.payload(mid)
    assert p["result_kind"] == "abandoned" and p["innings"] == [] and not any(t["winner"] for t in p["teams"])
    database.set_competition("wtc")
    mid = database.run("select match_id from gold.fact_matches where has_ball_by_ball limit 1").iloc[0, 0]
    p = MC.payload(mid)
    assert len(p["innings"]) >= 2 and all(i["bowling"] for i in p["innings"])
    database.set_competition("wc")


def test_walkover_has_no_invented_numbers() -> None:
    database.set_competition("wc")
    r = database.run("select match_id from gold.fact_matches where margin_type='walkover' limit 1")
    if not len(r):
        pytest.skip("no walkover in data")
    p = MC.payload(r.iloc[0, 0])
    assert p["innings"] == [] and p["stats"] == [] and "WALKOVER" in p["result"]
