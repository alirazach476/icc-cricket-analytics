# ruff: noqa: E501
"""Stage 11: leakage guarantees of the feature builder (synthetic data, plus the real table)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.features.match_features import (
    FEATURES_SCORE,
    FEATURES_WINNER,
    build_match_features,
    team_a_is_team1,
)

ROOT = Path(__file__).resolve().parents[1]
FEATURE_COLS = [c for c in set(FEATURES_WINNER + FEATURES_SCORE) if c not in ("year", "is_t20")]


def synthetic(n_days: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = [f"t{i}" for i in range(6)]
    rows = []
    for d in range(n_days):
        for k in range(2):  # two matches per day -> same-day isolation is exercised
            a, b = rng.choice(teams, 2, replace=False)
            w = a if rng.random() < 0.55 else b
            fi, si = int(rng.integers(120, 200)), int(rng.integers(100, 190))
            rows.append(
                dict(
                    match_id=f"m{d}_{k}",
                    tournament_id="T",
                    format="T20",
                    year=2020 + d // 15,
                    match_date=pd.Timestamp("2020-01-01") + pd.Timedelta(days=d),
                    is_knockout=False,
                    venue_id=f"v{k}",
                    team1_id=a,
                    team2_id=b,
                    winner_id=w,
                    toss_winner_id=a,
                    toss_decision="field",
                    is_completed=True,
                    is_walkover=False,
                    is_tie=False,
                    is_dls=False,
                    batting_first_team_id=a,
                    batting_second_team_id=b,
                    first_innings_runs=fi,
                    second_innings_runs=si,
                )
            )
    return pd.DataFrame(rows)


def test_features_ignore_the_future() -> None:
    """Rewriting every result after a cut-off date must not change any earlier match's features."""
    base = synthetic()
    cut = pd.Timestamp("2020-01-16")
    tampered = base.copy()
    late = tampered["match_date"] >= cut
    tampered.loc[late, "winner_id"] = tampered.loc[late, "team2_id"]
    tampered.loc[late, "first_innings_runs"] = 999
    tampered.loc[late, "second_innings_runs"] = 1
    f1, f2 = build_match_features(base), build_match_features(tampered)
    early = f1["match_date"] < cut
    pd.testing.assert_frame_equal(
        f1.loc[early, FEATURE_COLS].reset_index(drop=True),
        f2.loc[early, FEATURE_COLS].reset_index(drop=True),
    )
    # ...and the first day on/after the cut-off still only depends on the past: its features are equal too.
    first_late = f1["match_date"] == cut
    pd.testing.assert_frame_equal(
        f1.loc[first_late, FEATURE_COLS].reset_index(drop=True),
        f2.loc[first_late, FEATURE_COLS].reset_index(drop=True),
    )


def test_same_day_matches_do_not_see_each_other() -> None:
    base = synthetic()
    day = base["match_date"] == pd.Timestamp("2020-01-10")
    flipped = base.copy()
    flipped.loc[day & (flipped["match_id"].str.endswith("_0")), "winner_id"] = flipped["team2_id"]
    f1, f2 = build_match_features(base), build_match_features(flipped)
    second = f1["match_id"] == "m9_1"
    pd.testing.assert_frame_equal(
        f1.loc[second, FEATURE_COLS].reset_index(drop=True),
        f2.loc[second, FEATURE_COLS].reset_index(drop=True),
    )


def test_features_never_use_own_outcome() -> None:
    base = synthetic()
    flipped = base.copy()
    flipped["winner_id"] = flipped["team2_id"]  # change every outcome
    f1, f2 = build_match_features(base), build_match_features(flipped)
    first_day = f1["match_date"] == f1["match_date"].min()
    pd.testing.assert_frame_equal(
        f1.loc[first_day, FEATURE_COLS].reset_index(drop=True),
        f2.loc[first_day, FEATURE_COLS].reset_index(drop=True),
    )


def test_first_match_is_cold_start_neutral() -> None:
    f = build_match_features(synthetic())
    first = f[f["match_date"] == f["match_date"].min()]
    assert (first["elo_diff"] == 0).all() and (first["min_prior_matches"] == 0).all()
    assert np.allclose(first["win_rate_diff"], 0) and np.allclose(first["h2h_rate_a"], 0.5)


def test_orientation_is_deterministic_and_balanced() -> None:
    ids = [f"m{i}" for i in range(2000)]
    first = [team_a_is_team1(i) for i in ids]
    assert first == [team_a_is_team1(i) for i in ids]
    assert 0.45 < np.mean(first) < 0.55


def test_label_matches_orientation() -> None:
    base = synthetic()
    f = build_match_features(base).merge(base[["match_id", "winner_id"]], on="match_id")
    assert ((f["y_a_wins"] == 1.0) == (f["winner_id"] == f["team_a_id"])).all()


@pytest.mark.skipif(
    not (ROOT / "data/features/match_features.parquet").exists(), reason="features not built"
)
def test_real_feature_table_properties() -> None:
    f = pd.read_parquet(ROOT / "data/features/match_features.parquet")
    assert f["match_id"].is_unique
    assert 0.45 < f["y_a_wins"].mean() < 0.55, "label should be balanced by orientation"
    assert f[FEATURES_WINNER].notna().all().all()
    # No feature column may be an outcome column.
    assert not {"winner_id", "y_a_wins", "y_first_innings_runs"} & set(
        FEATURES_WINNER + FEATURES_SCORE
    )


def test_return_state_gives_final_ratings_without_changing_features() -> None:
    base = synthetic()
    plain = build_match_features(base)
    frame, elo = build_match_features(base, return_state=True)
    pd.testing.assert_frame_equal(plain, frame)
    assert set(elo) <= {("T20", f"t{i}") for i in range(6)}
    assert abs(sum(elo.values()) - 1500.0 * len(elo)) < 1e-6  # Elo only moves points between teams


def _two_team_matches(results: list[str]) -> pd.DataFrame:
    """Matches between teams a and b in a Test-like format; each result is 'a', 'b' or 'draw'."""
    rows = []
    for i, res in enumerate(results):
        rows.append(
            {
                "match_id": f"m{i}", "tournament_id": "T", "format": "Test", "year": 2020 + i // 5,
                "match_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=10 * i), "is_knockout": False,
                "venue_id": "v", "team1_id": "a", "team2_id": "b",
                "winner_id": {"a": "a", "b": "b", "draw": None}[res], "toss_winner_id": "a", "toss_decision": "bat",
                "is_completed": True, "is_walkover": False, "is_tie": False, "is_dls": False,
                "batting_first_team_id": "a", "batting_second_team_id": "b",
                "first_innings_runs": 300, "second_innings_runs": 250,
                "margin_type": "draw" if res == "draw" else "runs",
            }
        )
    return pd.DataFrame(rows)


def test_test_draw_counts_as_half_a_win_in_elo() -> None:
    # equal ratings: a draw changes nothing
    _, elo = build_match_features(_two_team_matches(["draw"]), return_state=True)
    assert elo[("Test", "a")] == elo[("Test", "b")] == 1500.0
    # after a wins, the stronger side a gives up points by drawing, b gains them, and the total is conserved
    _, after_win = build_match_features(_two_team_matches(["a"]), return_state=True)
    _, after_draw = build_match_features(_two_team_matches(["a", "draw"]), return_state=True)
    assert after_draw[("Test", "a")] < after_win[("Test", "a")]
    assert after_draw[("Test", "b")] > after_win[("Test", "b")]
    assert abs(sum(after_draw.values()) - 3000.0) < 1e-9


def test_abandoned_and_unlabelled_draws_do_not_move_elo_or_labels() -> None:
    m = _two_team_matches(["a", "draw"])
    m.loc[1, "is_completed"] = False  # abandoned: nothing was played
    _, elo = build_match_features(m, return_state=True)
    _, only_win = build_match_features(_two_team_matches(["a"]), return_state=True)
    assert elo == only_win
    f = build_match_features(_two_team_matches(["a", "draw"]))
    assert f["y_a_wins"].isna().tolist() == [False, True]  # a draw has no win/loss label
