# ruff: noqa: E501
"""Synthetic pitch/weather/day-night data stays labelled, deterministic and outcome-independent."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text
from src.synthetic import match_conditions as mc

ROOT = Path(__file__).resolve().parents[1]
GOLD_MATCHES = ROOT / "data" / "gold" / "fact_matches" / "part-0.parquet"
needs_gold = pytest.mark.skipif(not GOLD_MATCHES.exists(), reason="gold not built")


def test_deterministic_and_stable_under_additions() -> None:
    d = pd.Timestamp("2023-10-05")
    assert mc.generate_one("m1", d, "ODI") == mc.generate_one("m1", d, "ODI")
    assert mc.generate_one("m1", d, "ODI") != mc.generate_one("m2", d, "ODI")
    assert mc.generate_one("m1", d, "ODI", seed=1) != mc.generate_one("m1", d, "ODI", seed=2)
    a = mc.generate(
        pd.DataFrame({"match_id": ["m1", "m2"], "match_date": [d, d], "format": ["ODI", "T20"]})
    )
    b = mc.generate(
        pd.DataFrame(
            {"match_id": ["m0", "m1", "m2"], "match_date": [d] * 3, "format": ["T20", "ODI", "T20"]}
        )
    )
    pd.testing.assert_frame_equal(
        a.set_index("match_id").loc[["m1", "m2"]], b.set_index("match_id").loc[["m1", "m2"]]
    )


def test_rows_are_labelled_and_in_range() -> None:
    df = mc.generate(
        pd.DataFrame(
            {
                "match_id": [f"m{i}" for i in range(500)],
                "match_date": pd.Timestamp("2022-06-01"),
                "format": "T20",
            }
        )
    )
    assert df["is_synthetic"].all() and (df["generator_version"] == mc.GENERATOR_VERSION).all()
    assert set(df["pitch_type"]) <= set(mc.PITCH_TYPES) and set(df["day_night"]) <= {
        "day",
        "day_night",
    }
    assert (
        df["humidity_pct"].between(0, 100).all()
        and df["rain_probability_pct"].between(0, 100).all()
    )
    assert df["temperature_c"].between(8, 42).all() and df["wind_kmh"].between(0, 60).all()
    assert not df.loc[df["day_night"] == "day", "dew_expected"].any()  # dew only in day/night games
    assert df["match_id"].is_unique


def test_generator_signature_cannot_see_results() -> None:
    import inspect

    params = set(inspect.signature(mc.generate_one).parameters)
    assert params == {"match_id", "match_date", "fmt", "seed"}


@needs_gold
def test_values_are_independent_of_real_outcomes() -> None:
    m = pd.read_parquet(GOLD_MATCHES)
    syn = mc.generate(m).merge(m, on="match_id")
    won = syn[syn["winner_id"].notna() & syn["first_innings_runs"].notna()]
    # Random placeholders must carry no information about outcomes (weak, robust check).
    assert abs(won["temperature_c"].corr(won["first_innings_runs"])) < 0.2
    bat_first = (won["winner_id"] == won["batting_first_team_id"]).astype(float)
    assert abs(won["humidity_pct"].corr(bat_first)) < 0.2
    assert len(mc.generate(m)) == len(m)


@needs_gold
def test_written_table_covers_every_match() -> None:
    path = ROOT / "data" / "synthetic" / "match_conditions" / "part-0.parquet"
    if not path.exists():
        pytest.skip("synthetic data not generated")
    df = pd.read_parquet(path)
    assert set(df["match_id"]) == set(pd.read_parquet(GOLD_MATCHES)["match_id"])
    assert df["is_synthetic"].all()


def test_synthetic_data_is_kept_out_of_gold_and_ml() -> None:
    from src.features.match_features import FEATURES_SCORE, FEATURES_WINNER

    banned = {
        "pitch_type",
        "temperature_c",
        "humidity_pct",
        "day_night",
        "dew_expected",
        "is_synthetic",
    }
    assert not banned & set(FEATURES_WINNER + FEATURES_SCORE)
    assert not list((ROOT / "data" / "gold").glob("*synthetic*"))


def test_database_rejects_non_synthetic_flag() -> None:
    from src.database.connection import get_engine

    eng = get_engine()
    try:
        with eng.connect() as c:
            has = c.execute(
                text("select to_regclass('analytics.synthetic_match_conditions')")
            ).scalar()
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL not reachable")
    if has is None:
        pytest.skip("table not loaded")
    with pytest.raises(Exception, match="is_synthetic_only|violates"):
        with eng.begin() as c:
            c.execute(
                text(
                    "update analytics.synthetic_match_conditions set is_synthetic = false "
                    "where match_id = (select min(match_id) from analytics.synthetic_match_conditions)"
                )
            )
