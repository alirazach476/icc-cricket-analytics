"""Profiling code behaviour on small synthetic frames (never mixed with the real dataset)."""

from __future__ import annotations

import pandas as pd
from src.profiling.generate_data_audit import _md_table, build_findings
from src.profiling.profile_columns import column_kind, hashable, profile_column
from src.profiling.profile_dataset import file_collection_row, inventory_row, profile_dataframe


def test_numeric_column_stats_and_outliers() -> None:
    p = profile_column(pd.Series([1, 2, 3, 4, 100, None], name="total_runs"))
    assert p["kind"] == "numeric" and p["null_count"] == 1
    assert p["min"] == 1 and p["max"] == 100 and p["median"] == 3
    assert p["outliers_iqr"] == 1


def test_negative_values_flagged_only_for_nonnegative_columns() -> None:
    assert profile_column(pd.Series([1, -2], name="wickets"))["negative_values"] == 1
    assert profile_column(pd.Series([1, -2], name="net_run_rate"))["negative_values"] is None


def test_date_detection_object_and_string_columns() -> None:
    import datetime as dt

    assert (
        column_kind(pd.Series([dt.date(2007, 9, 11), dt.date(2012, 10, 7)], name="match_date"))
        == "datetime"
    )
    p = profile_column(pd.Series(["2007-09-11", "2026-03-08"], name="start_date"))
    assert (p["min"], p["max"]) == ("2007-09-11", "2026-03-08")


def test_hashable_handles_lists_and_dicts() -> None:
    s = hashable(pd.Series([[1, 2], [1, 2], {"a": 1}], name="x"))
    assert s.nunique() == 2


def test_dataframe_profile_flags_duplicates_nulls_and_empties() -> None:
    df = pd.DataFrame(
        {
            "match_id": ["a", "b", "b"],
            "tournament_id": ["ODI_M_2003", "T20_M_2007", "T20_M_2007"],
            "umpires": [None, None, None],
            "note": ["x", " ", "x"],
        }
    )
    prof = profile_dataframe("t", df, key="match_id")
    assert prof["duplicate_keys"] == 1
    assert (
        prof["tournaments_covered"] == 2
        and prof["odi_tournaments"] == 1
        and prof["t20_tournaments"] == 1
    )
    assert any("umpires: 100% null" in i for i in prof["issues"])
    assert any("blank strings" in i for i in prof["issues"])
    assert inventory_row(prof)["rows"] == 3


def test_business_duplicates_ignore_surrogate_keys_and_timestamps() -> None:
    df = pd.DataFrame({"id": [1, 2], "name": ["x", "x"], "created_at": ["t1", "t2"]})
    prof = profile_dataframe("t", df, key="id")
    assert prof["duplicate_rows"] == 0
    assert prof["duplicate_rows_ignoring_keys"] == 1


def test_empty_frame_is_reported_not_crashing() -> None:
    prof = profile_dataframe("empty", pd.DataFrame({"a": []}))
    assert "empty dataset" in prof["issues"]


def test_file_collection_row_counts_files(tmp_path) -> None:
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.json").write_text("{}")
    row = file_collection_row("c", tmp_path, "*.json", fmt="json")
    assert row["rows"] == 2


def test_findings_rank_identity_and_coverage_issues() -> None:
    cov = pd.DataFrame(
        {
            "tournament_id": ["T20_M_2007"],
            "completed_matches": [26],
            "completed_with_deliveries": [0],
            "completed_without_deliveries": [26],
        }
    )
    ctx = {
        "identity": {
            "names_split_across_sources": 3,
            "delivery_batters_with_cricsheet_id": 5,
            "scorecard_batters_distinct": 7,
            "delivery_and_scorecard_player_id_overlap": 0,
            "teams_named_as_their_id": [],
            "short_names_not_uppercase_abbrev": [],
        },
        "cricket": {
            "tournament_coverage": cov,
            "venue_variants": pd.DataFrame(),
            "stage_distribution": pd.DataFrame({"match_stage": ["Other"], "matches": [2]}),
            "entity_counts": {"venues_distinct_text": 3, "cities_distinct_text": 3},
        },
        "relationships": [
            {
                "status": "fail",
                "relationship": "r",
                "violating_rows": 1,
                "checked_rows": 4,
                "detail": "",
                "examples": "(1)",
            }
        ],
        "profiles": [],
    }
    findings = build_findings(ctx)
    high = [f for f in findings if f["severity"] == "High"]
    assert {f["area"] for f in high} == {"Identity", "Coverage", "Integrity"}
    assert any("None of" in f["evidence"] or "none of" in f["evidence"] for f in high)
    assert any("Other" in f["finding"] for f in findings)


def test_md_table_escapes_pipes_and_handles_empty() -> None:
    assert _md_table(pd.DataFrame()) == "_none_\n"
    assert "a/b" in _md_table(pd.DataFrame({"x": ["a|b"]}))
