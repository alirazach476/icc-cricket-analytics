"""Medallion layers: bronze immutability, identity resolution, silver cleaning, gold metrics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from src.ingestion.bronze import latest_batch, read_bronze, verify_bronze, write_batch
from src.transformations.gold import PHASES, _phase, fact_super_over_performances, mart_batting
from src.transformations.identity import (
    RosterPlayer,
    build_identity_map,
    cricsheet_slug,
    norm,
    resolve_name,
)
from src.transformations.silver import _group_clusters, parse_result, resolve_team_aliases

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ bronze
def _t(n: int) -> datetime:
    return datetime(2026, 1, 1, 0, 0, n, tzinfo=UTC)


def test_bronze_is_idempotent_versioned_and_tamper_evident(tmp_path) -> None:
    df = pd.DataFrame({"match_id": ["1", "2"], "runs": [10, 20]})
    first = write_batch(tmp_path, "matches", df, "src", now=_t(1))
    assert first["status"] == "written"
    assert write_batch(tmp_path, "matches", df, "src", now=_t(2))["status"] == "unchanged"
    changed = pd.DataFrame({"match_id": ["1", "2"], "runs": [10, 21]})
    second = write_batch(tmp_path, "matches", changed, "src", now=_t(3))
    assert second["status"] == "written" and second["batch_id"] != first["batch_id"]
    assert (
        tmp_path / "data/bronze/matches" / f"batch_id={first['batch_id']}"
    ).exists()  # old batch kept
    assert read_bronze(tmp_path, "matches")["runs"].tolist() == [10, 21]
    assert latest_batch(tmp_path, "matches")["rows"] == 2
    assert verify_bronze(tmp_path) == []


def test_bronze_refuses_to_overwrite_an_existing_batch(tmp_path) -> None:
    write_batch(tmp_path, "x", pd.DataFrame({"a": [1]}), "s", now=_t(1))
    with pytest.raises(FileExistsError):
        write_batch(tmp_path, "x", pd.DataFrame({"a": [2]}), "s", now=_t(1))


def test_bronze_verify_detects_modified_file(tmp_path) -> None:
    rec = write_batch(tmp_path, "x", pd.DataFrame({"a": [1, 2]}), "s", now=_t(1))
    path = tmp_path / "data/bronze/x" / f"batch_id={rec['batch_id']}" / "part-0.parquet"
    tampered = pd.read_parquet(path)
    tampered.loc[0, "a"] = 99
    tampered.to_parquet(path, index=False)
    assert verify_bronze(tmp_path) == ["x: content hash differs from manifest"]


# ------------------------------------------------------------------ identity
ROSTER = [
    RosterPlayer("espn_1", "Jonny Bairstow", "JM Bairstow", "t1"),
    RosterPlayer("espn_2", "Dhananjaya de Silva", "PHKD Mendis", "t2"),
    RosterPlayer("espn_3", "Wanindu Hasaranga", "PWH de Silva", "t2"),
    RosterPlayer("espn_4", "Muhammad Waseem", "M Waseem", "t3"),
    RosterPlayer("espn_5", "Ali Khan", "A Khan", "t3"),
    RosterPlayer("espn_6", "Ali Khan", "AS Khan", "t3"),
]


def test_resolve_by_batting_name_and_full_name() -> None:
    assert resolve_name("JM Bairstow", ROSTER) == ("espn_1", "batting_name")
    assert resolve_name("Jonny Bairstow", ROSTER) == ("espn_1", "full_name")


def test_resolve_reordered_name_and_accents() -> None:
    assert resolve_name("Waseem Muhammad", ROSTER) == ("espn_4", "token_set")
    assert norm("Nandré Burger") == "nandre burger"


def test_two_players_with_the_same_exact_name_are_refused_not_guessed() -> None:
    assert resolve_name("Ali Khan", ROSTER) == (None, None)


def test_shared_surname_alone_never_resolves() -> None:
    # 'PWH de Silva' is Hasaranga's batting name here, but with it absent the surname rule must NOT
    # pick Dhananjaya de Silva (the mistake that mis-assigned 7 of 8 cases against real scorecards).
    roster = [RosterPlayer("espn_2", "Dhananjaya de Silva", "PHKD Mendis", "t2")]
    assert resolve_name("PWH de Silva", roster) == (None, None)


def test_initials_resolve_when_unique() -> None:
    roster = [RosterPlayer("espn_9", "Jonathan Mark Bairstow", "Jonathan Bairstow")]
    assert resolve_name("JM Bairstow", roster) == ("espn_9", "initials")


def test_cricsheet_slug_matches_the_loader_convention() -> None:
    assert cricsheet_slug("AB de Villiers") == "ab_de_villiers"


def test_elimination_resolves_the_last_unmatched_player_of_a_team() -> None:
    deliveries = pd.DataFrame(
        {
            "match_id": ["m"] * 4,
            "innings_number": [1, 1, 1, 1],
            "batter_id": ["JM Bairstow", "Legal Name X", "JM Bairstow", "Legal Name X"],
            "non_striker_id": ["Legal Name X", "JM Bairstow", "Legal Name X", "JM Bairstow"],
            "bowler_id": ["B Bowler"] * 4,
            "dismissed_player_id": [None] * 4,
            "fielder_id": [None] * 4,
        }
    )
    players = pd.DataFrame(
        {
            "match_id": ["m", "m", "m"],
            "player_id": ["espn_1", "espn_2", "espn_7"],
            "full_name": ["Jonny Bairstow", "Different Display Name", "Bowler Person"],
            "batting_name": ["JM Bairstow", "D Name", "B Bowler"],
        }
    )
    batting = pd.DataFrame(
        {
            "match_id": ["m", "m"],
            "player_id": ["espn_1", "espn_2"],
            "team_id": ["t1", "t1"],
            "runs": [5, 5],
            "balls_faced": [4, 4],
        }
    )
    bowling = pd.DataFrame({"match_id": ["m"], "player_id": ["espn_7"], "team_id": ["t2"]})
    fielding = pd.DataFrame({"match_id": [], "player_id": [], "team_id": []})
    innings = pd.DataFrame(
        {
            "match_id": ["m"],
            "innings_number": [1],
            "batting_team_id": ["t1"],
            "bowling_team_id": ["t2"],
        }
    )
    out, summary = build_identity_map(deliveries, players, batting, bowling, fielding, innings)
    got = out.set_index("source_name")[["resolved_player_id", "method"]]
    assert got.loc["Legal Name X"].tolist() == ["espn_2", "elimination"]
    assert got.loc["JM Bairstow"].tolist() == ["espn_1", "batting_name"]
    assert summary["names_resolved_pct"] == 100


# ------------------------------------------------------------------ silver
def test_parse_result_variants() -> None:
    r = parse_result("New Zealand won by 9 wickets (with 82 balls remaining)", "RESULT")
    assert (r["margin_type"], r["margin_value"], r["balls_remaining"], r["is_dls"]) == (
        "wickets",
        9,
        82,
        False,
    )
    assert parse_result("India won by 89 runs (D/L method)", "RESULT")["is_dls"] is True
    assert parse_result("Ireland won by 5 runs (DLS method)", "RESULT")["is_dls"] is True
    tie = parse_result("Match tied (England won on boundary count)", "RESULT")
    assert (
        tie["is_tie"]
        and tie["tie_break_winner_name"] == "England"
        and tie["tie_break_method"] == "boundary count"
    )
    so = parse_result("Match tied (South Africa won the 2nd Super Over)", "RESULT")
    assert so["tie_break_method"] == "super over" and so["tie_break_winner_name"] == "South Africa"
    plain = parse_result("Match tied", "RESULT")
    assert plain["is_tie"] and plain["tie_break_winner_name"] is None
    assert parse_result("Zimbabwe won (walkover without a ball bowled)", "RESULT")["is_walkover"]
    assert parse_result("No result", "NO RESULT")["margin_type"] == "no_result"
    assert (
        parse_result("Match abandoned without a ball bowled", "ABANDONED")["margin_type"]
        == "abandoned"
    )
    assert parse_result("India won by 1 run", "RESULT")["margin_value"] == 1


def test_team_aliases_map_only_when_unambiguous() -> None:
    m = pd.DataFrame(
        {
            "match_id": ["1", "2", "3", "4"],
            "team1_id": ["N", "N", "A", "A"],
            "team2_id": ["X", "Y", "B", "C"],
            "winner_id": ["ALIAS_N", "N", None, "ALIAS_Q"],
            "toss_winner_id": [None, "ALIAS_N", None, None],
        }
    )
    out = resolve_team_aliases(m).set_index("alias_id")["mapped_team_id"]
    assert out["ALIAS_N"] == "N"  # N is the only team playing in every match that references it
    assert pd.isna(out["ALIAS_Q"]) or out["ALIAS_Q"] in {"A", "C"}


def test_stage_rounds_split_even_when_boundary_day_is_shared() -> None:
    # Real T20 2014 date ranges: first-round Group B ends 3/21 and Super Group 2 starts that same day.
    ranges = {
        "First Round Group A": ("2014-03-16", "2014-03-20"),
        "First Round Group B": ("2014-03-17", "2014-03-21"),
        "Group 2": ("2014-03-21", "2014-04-01"),
        "Group 1": ("2014-03-22", "2014-03-31"),
    }
    standings, dates, n = [], [], 0
    for g, (first, last) in ranges.items():
        ids = [str(n), str(n + 1)]
        n += 2
        dates += [(ids[0], first), (ids[1], last)]
        standings += [
            {
                "tournament_id": "T",
                "group_name": g,
                "team_id": f"{g}-{k}",
                "group_match_ids": json.dumps(ids),
            }
            for k in range(5)
        ]
    matches = pd.DataFrame(dates, columns=["match_id", "match_date"])
    matches["match_date"] = pd.to_datetime(matches["match_date"]).dt.date
    gm = _group_clusters(pd.DataFrame(standings), matches)
    labels = gm.drop_duplicates("group_name").set_index("group_name")["round_label"].to_dict()
    assert (
        labels["First Round Group A"] == "First Round"
        and labels["First Round Group B"] == "First Round"
    )
    assert labels["Group 1"] == "Super Ten" and labels["Group 2"] == "Super Ten"


# ------------------------------------------------------------------ gold
def test_phase_boundaries_by_format() -> None:
    over = pd.Series([1, 6, 7, 15, 16, 20, 10, 11, 40, 41, 50])
    fmt = pd.Series(["T20"] * 6 + ["ODI"] * 5)
    assert _phase(over, fmt).tolist() == [
        "powerplay",
        "powerplay",
        "middle",
        "middle",
        "death",
        "death",
        "powerplay",
        "middle",
        "middle",
        "death",
        "death",
    ]
    assert PHASES["T20"] == (6, 15)


def test_batting_mart_average_counts_not_outs_correctly() -> None:
    fp = pd.DataFrame(
        {
            "match_id": ["a", "b", "c", "d"],
            "player_id": ["p"] * 4,
            "tournament_id": ["T"] * 4,
            "format": ["ODI"] * 4,
            "year": [2023] * 4,
            "team_id": ["t"] * 4,
            "did_bat": [True] * 4,
            "runs": [100, 50, 0, 30],
            "balls_faced": [100, 50, 2, 30],
            "fours": [10, 5, 0, 2],
            "sixes": [2, 0, 0, 1],
            "is_out": [True, False, True, True],
        }
    )
    r = mart_batting(fp, True).iloc[0]
    assert (r["runs"], r["innings"], r["not_outs"]) == (180, 4, 1)
    assert r["average"] == 60.0  # 180 / (4 - 1)
    assert (r["hundreds"], r["fifties"], r["ducks"], r["highest_score"]) == (1, 1, 1, 100)
    assert r["strike_rate"] == pytest.approx(180 / 182 * 100, abs=0.01)


def test_super_over_rows_are_kept_out_of_regular_stats() -> None:
    S = {
        "innings": pd.DataFrame(
            {
                "match_id": ["m", "m", "m"],
                "innings_number": [1, 2, 3],
                "is_super_over": [False, False, True],
            }
        ),
        "batting": pd.DataFrame(
            {
                "match_id": ["m", "m"],
                "innings_number": [1, 3],
                "player_id": ["p", "p"],
                "team_id": ["t", "t"],
                "runs": [20, 6],
                "balls_faced": [15, 3],
                "fours": [1, 0],
                "sixes": [0, 1],
                "is_out": [True, False],
            }
        ),
        "bowling": pd.DataFrame(
            {
                "match_id": [],
                "innings_number": [],
                "player_id": [],
                "team_id": [],
                "balls_bowled": [],
                "runs_conceded": [],
                "wickets": [],
            }
        ),
    }
    so = fact_super_over_performances(S)
    assert so["runs"].tolist() == [6] and so["innings_number"].tolist() == [3]


# ------------------------------------------------------------------ real built layers (skipped if absent)
needs_gold = pytest.mark.skipif(
    not (ROOT / "data/gold/mart_batting").exists(), reason="gold layer not built"
)


@needs_gold
def test_gold_matches_independently_known_records() -> None:
    from src.transformations.gold import read_gold

    mb = read_gold(ROOT, "mart_batting")
    mw = read_gold(ROOT, "mart_bowling")
    names = read_gold(ROOT, "dim_players").set_index("player_id")["full_name"]
    mb["player"] = mb["player_id"].map(names)
    mw["player"] = mw["player_id"].map(names)

    def bat(t, p):
        return mb[(mb.tournament_id == t) & (mb.player == p)].iloc[0]

    kohli = bat("ODI_M_2023", "Virat Kohli")
    assert (kohli.runs, kohli.matches, kohli.hundreds, kohli.highest_score, kohli.average) == (
        765,
        11,
        3,
        117,
        95.62,
    )
    assert bat("ODI_M_2003", "Sachin Tendulkar").runs == 673
    assert bat("ODI_M_2015", "Martin Guptill").highest_score == 237
    assert bat("ODI_M_2019", "Rohit Sharma").hundreds == 5
    shami = mw[(mw.tournament_id == "ODI_M_2023") & (mw.player == "Mohammed Shami")].iloc[0]
    assert (shami.wickets, shami.best_figures) == (24, "7/57")
    starc = mw[(mw.tournament_id == "ODI_M_2015") & (mw.player == "Mitchell Starc")].iloc[0]
    assert starc.wickets == 22


@needs_gold
def test_gold_facts_have_unique_keys_and_no_orphans() -> None:
    from src.transformations.gold import read_gold

    fp = read_gold(ROOT, "fact_player_performances")
    fm = read_gold(ROOT, "fact_matches")
    players = set(read_gold(ROOT, "dim_players")["player_id"])
    teams = set(read_gold(ROOT, "dim_teams")["team_id"])
    assert not fp.duplicated(["match_id", "player_id"]).any()
    assert fm["match_id"].is_unique and len(fm) == 719
    assert set(fp["player_id"]) <= players
    assert set(fm["team1_id"]) | set(fm["team2_id"]) | set(fm["winner_id"].dropna()) <= teams


@needs_gold
def test_silver_fixed_the_stage3_defects() -> None:
    from src.transformations.silver import read_silver

    m = read_silver(ROOT, "matches")
    assert not (
        m["winner_id"].notna()
        & ~m["winner_id"].eq(m["team1_id"])
        & ~m["winner_id"].eq(m["team2_id"])
    ).any()
    assert not (
        m["toss_winner_id"].notna()
        & ~m["toss_winner_id"].eq(m["team1_id"])
        & ~m["toss_winner_id"].eq(m["team2_id"])
    ).any()
    assert not m["stage"].eq("Other").any()
    final_2019 = m[(m.tournament_id == "ODI_M_2019") & (m.stage == "Final")].iloc[0]
    assert final_2019.winner_id == "espn_1" and final_2019.winner_source == "tie_break_text"
    inn = read_silver(ROOT, "innings")
    assert inn["total_runs"].notna().all() and inn["wickets"].notna().all()
    d = read_silver(ROOT, "deliveries")
    assert d["batter_id"].str.startswith("espn_").mean() > 0.999


# ------------------------------------------------------------------ limitation fixes (real built layers)
@needs_gold
def test_bowl_out_winner_comes_from_evidenced_override_and_other_ties_stay_open() -> None:
    from src.transformations.silver import read_silver

    m = read_silver(ROOT, "matches").set_index("match_id")
    bowl_out = m.loc["287862"]
    assert (bowl_out.winner_id, bowl_out.winner_source, bowl_out.tie_break_method) == (
        "espn_6",
        "manual_override",
        "bowl-out",
    )
    open_ties = m[m["is_tie"] & ~m["has_winner"]].index.tolist()
    assert sorted(open_ties) == [
        "247461",
        "433568",
        "65233",  # 1999 semi-final: tied; Australia went through on Super Six position, not a tie-break
        "65272",
    ]  # genuine ties with no tie-break in the data
    assert (m["winner_source"] == "manual_override").sum() == 1


def test_override_and_alias_config_files_are_well_formed() -> None:
    ov = pd.read_csv(ROOT / "config/result_overrides.csv", dtype=str)
    assert set(ov.columns) >= {
        "match_id",
        "winner_team_name",
        "tie_break_method",
        "reason",
        "evidence",
    }
    assert ov["evidence"].str.len().min() > 40  # every override must carry its evidence
    va = pd.read_csv(ROOT / "config/venue_aliases.csv", dtype=str)
    assert not set(va["alias_name"]) & set(
        va["canonical_name"]
    )  # no chains: canonical names are final


@needs_gold
def test_venues_are_merged_for_renamed_grounds_and_variants_are_kept() -> None:
    from src.transformations.gold import read_gold

    v = read_gold(ROOT, "dim_venues").set_index("venue_name")
    assert len(v) == 91 and v["possible_duplicate_of"].isna().all()
    assert "Feroz Shah Kotla" in v.loc["Arun Jaitley Stadium, Delhi", "name_variants"]
    assert v.loc["M Chinnaswamy Stadium, Bengaluru", "matches"] == 13
    assert "Perth Stadium" in v.index and any(
        "Western Australia" in n for n in v.index
    )  # different grounds stay apart
    fm = read_gold(ROOT, "fact_matches")
    assert fm["venue_id"].notna().all() and fm["venue_id"].nunique() == 91


@needs_gold
def test_every_match_has_ball_by_ball_or_an_explicit_gap_reason() -> None:
    from src.transformations.gold import read_gold

    fm = read_gold(ROOT, "fact_matches")
    assert len(fm) == 719
    assert not (fm["has_ball_by_ball"] & fm["ball_by_ball_gap_reason"].notna()).any()
    assert not (~fm["has_ball_by_ball"] & fm["ball_by_ball_gap_reason"].isna()).any()
    reasons = fm["ball_by_ball_gap_reason"].value_counts().to_dict()
    assert set(reasons) <= {
        "not_in_cricsheet_world_cup_bundle",
        "no_result_or_abandoned",
        "walkover_no_play",
    }
    cov = read_gold(ROOT, "mart_data_coverage")
    assert (
        len(cov) == 17
        and (cov["teams"] == cov["teams_with_squad"]).all()
        and cov["has_player_of_tournament"].all()
    )
    assert (
        int(cov["played_without_ball_by_ball"].sum())
        == reasons["not_in_cricsheet_world_cup_bundle"]
    )
