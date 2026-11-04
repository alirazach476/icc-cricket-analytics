# ruff: noqa: E501
"""Champions Trophy and World Test Championship data: documented results and internal consistency."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
CT = ROOT / "data" / "competitions" / "ct" / "data" / "gold"
WTC = ROOT / "data" / "competitions" / "wtc" / "data" / "gold"

pytestmark = pytest.mark.skipif(
    not (CT / "fact_matches").exists(), reason="run scripts/run_competitions.py"
)


def g(root: Path, name: str) -> pd.DataFrame:
    return pd.read_parquet(root / name / "part-0.parquet")


def test_champions_trophy_editions_and_no_2026() -> None:
    t = g(CT, "dim_tournaments")
    assert sorted(t["year"]) == [
        2002,
        2004,
        2006,
        2009,
        2013,
        2017,
        2025,
    ]  # no 2026: the next one is 2029
    assert set(t["format"]) == {"ODI"}


def test_champions_trophy_has_every_scheduled_match_including_abandoned() -> None:
    m = g(CT, "fact_matches")
    assert m.groupby("year").size().to_dict() == {
        2002: 16,
        2004: 15,
        2006: 21,
        2009: 15,
        2013: 15,
        2017: 15,
        2025: 15,
    }
    y25 = m[m["year"] == 2025]
    assert (
        int((y25["result_type"] != "RESULT").sum()) == 3
    )  # two abandoned without a ball + one rained off
    assert int(y25["winner_id"].notna().sum()) == 12


def test_champions_trophy_winners_awards_and_joint_title() -> None:
    t = g(CT, "mart_tournament_summary").set_index("year")
    assert {y: (t.loc[y, "winner"], t.loc[y, "runner_up"]) for y in t.index} == {
        2002: ("India & Sri Lanka (joint)", None),
        2004: ("West Indies", "England"),
        2006: ("Australia", "West Indies"),
        2009: ("Australia", "New Zealand"),
        2013: ("India", "England"),
        2017: ("Pakistan", "India"),
        2025: ("India", "New Zealand"),
    }
    assert {y: t.loc[y, "player_of_tournament"] for y in t.index if y != 2002} == {
        2004: "Ramnaresh Sarwan",
        2006: "Chris Gayle",
        2009: "Ricky Ponting",
        2013: "Shikhar Dhawan",
        2017: "Hasan Ali",
        2025: "Rachin Ravindra",
    }
    assert t.loc[2002, "player_of_tournament"] is None


def test_champions_trophy_squads_and_points_tables() -> None:
    sq = g(CT, "fact_squads")
    assert (
        set(sq[sq["tournament_id"] == "CT_M_2025"].groupby("team_id").size().index)
        and len(sq[sq["tournament_id"] == "CT_M_2025"]) >= 100
    )
    assert set(sq[sq["tournament_id"] == "CT_M_2017"]["source"]) == {"espncricinfo"}
    assert (
        sq[sq["tournament_id"] == "CT_M_2002"]["source"] == "playing_xi"
    ).all()  # no squad list exists for the oldest editions
    st = g(CT, "fact_tournament_standings")
    assert set(st["tournament_id"]) == set(g(CT, "dim_tournaments")["tournament_id"])


def test_2017_final_scorecard() -> None:
    m = g(CT, "fact_matches")
    f = m[(m["year"] == 2017) & (m["stage"] == "Final")].iloc[0]
    assert (f["winner_name"], f["margin_type"], f["margin_value"]) == ("Pakistan", "runs", 180)
    assert (f["first_innings_runs"], f["second_innings_runs"]) == (338, 158)
    p = g(CT, "fact_player_performances")
    d = g(CT, "dim_players").set_index("player_id")
    zaman = p[
        (p["match_id"] == f["match_id"])
        & p["player_id"].map(d["full_name"]).str.contains("Fakhar", na=False)
    ]
    assert len(zaman) == 1 and zaman.iloc[0]["runs"] == 114


def test_players_keep_their_world_cup_identity() -> None:
    wc = g(ROOT / "data" / "gold", "dim_players")
    ct = g(CT, "dim_players")
    both = set(wc["player_id"]) & set(ct["player_id"])
    assert len(both) > 100  # the same people carry the same player_id across competitions


def test_wtc_cycles() -> None:
    t = g(WTC, "mart_tournament_summary").set_index("year")
    assert list(t.index) == [2021, 2023, 2025, 2027]
    assert list(t["matches"]) == [
        61,
        70,
        70,
        44,
    ]  # 5 matches of 2019-21 were postponed (never played)
    assert [(t.loc[y, "winner"], t.loc[y, "runner_up"]) for y in (2021, 2023, 2025)] == [
        ("New Zealand", "India"),
        ("Australia", "India"),
        ("South Africa", "Australia"),
    ]
    assert t.loc[2027, "winner"] is None  # the 2025-27 cycle has no final yet


def test_wtc_finals_results() -> None:
    m = g(WTC, "fact_matches")
    f = m[m["stage"] == "Final"].sort_values("match_date")
    assert list(f["year"]) == [2021, 2023, 2025]
    assert list(zip(f["winner_name"], f["margin_type"], f["margin_value"], strict=True)) == [
        ("New Zealand", "wickets", 8),
        ("Australia", "runs", 209),
        ("South Africa", "wickets", 5),
    ]
    assert list(f["match_runs"]) == [776, 1269, 839]


def test_wtc_2023_innings() -> None:
    fi = g(WTC, "fact_innings")
    fm = g(WTC, "fact_matches")
    final = fm[(fm["year"] == 2023) & (fm["stage"] == "Final")].iloc[0]["match_id"]
    inn = fi[fi["match_id"] == final].sort_values("innings_number")
    assert list(zip(inn["batting_team"], inn["total_runs"], inn["wickets"], strict=True)) == [
        ("Australia", 469, 10),
        ("India", 296, 10),
        ("Australia", 270, 8),
        ("India", 234, 10),
    ]
    assert list(inn["is_chase"]) == [False, False, False, True]


def test_bowling_is_not_double_counted_for_two_innings_batters() -> None:
    p = g(WTC, "fact_player_performances")
    assert not p.duplicated(["match_id", "player_id", "batting_innings"]).any()
    per_match = p.groupby("match_id")["wickets"].sum()
    fi = g(WTC, "fact_innings")
    # bowler wickets exclude run-outs, so they can only be at or below the wickets that fell
    assert (per_match <= fi.groupby("match_id")["wickets"].sum().reindex(per_match.index)).all()


@pytest.mark.parametrize("root", [CT, WTC])
def test_scorecards_add_up_to_the_ball_by_ball(root: Path) -> None:
    fi = g(root, "fact_innings")
    fd = g(root, "fact_deliveries")
    runs = fd.groupby(["match_id", "innings_number"])["total_runs"].sum()
    # an innings total equals the sum of its deliveries, plus penalty runs when they are awarded outside the ball-by-ball
    f = fi.set_index(["match_id", "innings_number"])
    f = f[
        f.index.isin(runs.index)
    ]  # matches that only exist as ESPNcricinfo scorecards have no deliveries
    diff = f["total_runs"] - runs.reindex(f.index)
    assert len(f) > 100 and ((diff == 0) | (diff == f["penalties"].fillna(0))).all()
    p = g(root, "fact_player_performances")
    bat = p[p["did_bat"]].groupby("match_id")["runs"].sum()
    extras = fi.groupby("match_id")["extras"].sum()
    total = fi.groupby("match_id")["total_runs"].sum()
    assert ((bat + extras) == total.reindex(bat.index)).all()
    assert (fi["wickets"] <= 10).all()


def test_matches_have_two_teams_and_a_winner_when_decided() -> None:
    m = g(CT, "fact_matches")
    assert (m["team1_id"] != m["team2_id"]).all()
    decided = m[m["winner_id"].notna()]
    assert decided["winner_id"].isin(set(decided["team1_id"]) | set(decided["team2_id"])).all()


def test_every_innings_matches_the_espncricinfo_scorecard() -> None:
    """Ball-by-ball totals (Cricsheet) against the independent ESPNcricinfo scorecards."""
    import json

    checked = 0
    for code, root in (("CT", CT), ("WTC", WTC)):
        fi = g(root, "fact_innings").set_index(["match_id", "innings_number"])[
            ["total_runs", "wickets"]
        ]
        for f in (ROOT / "data" / "competitions" / "espn").glob(f"{code}_M_*/scorecards/*.json"):
            card = json.loads(f.read_text(encoding="utf-8"))
            for i in card.get("innings", []):
                key = (card["match_id"], i["innings_number"])
                if key in fi.index:
                    assert (int(fi.loc[key, "total_runs"]), int(fi.loc[key, "wickets"])) == (
                        int(i["total_runs"]),
                        int(i["wickets"]),
                    ), key
                    checked += 1
    assert checked > 1000


# ---------------------------------------------------------------- ICC Men's Cricket World Cup 2027 (not played yet)
WC27 = ROOT / "data" / "competitions" / "wc27" / "data" / "gold"


@pytest.mark.skipif(
    not (WC27 / "schedule").exists(), reason="run scripts/run_competitions.py --wc2027"
)
class TestWorldCup2027:
    def test_schedule_shape(self) -> None:
        s = g(WC27, "schedule")
        assert len(s) == 57 and s["match_no"].tolist() == list(range(1, 58))
        assert s["phase"].value_counts().to_dict() == {
            "Group Stage": 30,
            "Super 7": 21,
            "Super Series": 3,
            "Semi-final": 2,
            "Final": 1,
        }
        assert (
            str(s["date"].min())[:10] == "2027-10-02" and str(s["date"].max())[:10] == "2027-11-21"
        )
        final = s[s["phase"] == "Final"].iloc[0]
        assert (final["city"], str(final["date"])[:10]) == ("Johannesburg", "2027-11-21")

    def test_both_sources_agree_on_every_fixture(self) -> None:
        s = g(WC27, "schedule")
        assert s["sources_agree"].astype(bool).all()

    def test_venues(self) -> None:
        v = g(WC27, "venues")
        assert len(v) == 12 and v["matches"].sum() == 57
        assert v.groupby("country").size().to_dict() == {
            "Namibia": 1,
            "South Africa": 8,
            "Zimbabwe": 3,
        }
        assert v.set_index("city").loc["Johannesburg", "capacity"] == 34000

    def test_teams_and_groups(self) -> None:
        t = g(WC27, "teams")
        assert len(t) == 12 and int(t["confirmed"].sum()) == 10
        assert sorted(t[t["group"] == "A"]["team"]) == [
            "Afghanistan",
            "Australia",
            "India",
            "Pakistan",
            "Qualifier A",
            "Zimbabwe",
        ]
        assert set(t[t["status"] == "host"]["team"]) == {"South Africa", "Zimbabwe"}
        s = g(WC27, "schedule")
        gs = s[s["phase"] == "Group Stage"]
        for team in t[t["confirmed"]]["team"]:
            assert (
                int(((gs["team1"] == team) | (gs["team2"] == team)).sum()) == 5
            )  # each team plays the other five

    def test_no_results_are_invented(self) -> None:
        cols = set(g(WC27, "schedule").columns)
        assert not cols & {"winner", "result", "score", "runs"}
