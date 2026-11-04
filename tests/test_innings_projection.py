# ruff: noqa: E501
"""Model 2: live first-innings projection - features cannot see the future, evaluation is time-aware."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.ml import innings_projection as ip

ROOT = Path(__file__).resolve().parents[1]


def toy_balls(match_id="m1", overs=20, runs_per_ball=1, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for o in range(1, overs + 1):
        for _b in range(6):
            r = int(rng.integers(0, 5)) if runs_per_ball is None else runs_per_ball
            rows.append(
                dict(
                    match_id=match_id,
                    tournament_id="T1",
                    format="T20",
                    match_date=pd.Timestamp("2020-01-01"),
                    over_number=o,
                    total_runs=r,
                    is_wicket=False,
                    is_legal_ball=True,
                    is_boundary=r >= 4,
                    is_dot_ball=r == 0,
                    is_dls=False,
                )
            )
    return pd.DataFrame(rows)


def ctx(match_id="m1") -> pd.DataFrame:
    return pd.DataFrame({"match_id": [match_id], **{c: [0.0] for c in ip.CONTEXT}})


def test_checkpoint_features_are_exact() -> None:
    s = ip.build_samples(toy_balls(runs_per_ball=1), ctx())
    row = s[s["checkpoint"] == 10].iloc[0]
    assert row["score"] == 60 and row["overs"] == 10 and row["run_rate"] == 6.0 and row["y"] == 120
    assert row["projected_linear"] == 60 + 6.0 * 10
    assert row["recent_run_rate"] == 6.0 and row["wickets"] == 0


def test_features_at_a_checkpoint_ignore_later_balls() -> None:
    a = toy_balls(runs_per_ball=None, seed=1)
    b = a.copy()
    late = b["over_number"] > 10
    b.loc[late, "total_runs"] = 6  # change only what happens after over 10
    b.loc[late, "is_boundary"] = True
    sa, sb = ip.build_samples(a, ctx()), ip.build_samples(b, ctx())
    for k in (4, 6, 8, 10):
        pd.testing.assert_frame_equal(
            sa[sa.checkpoint == k][ip.FEATURES].reset_index(drop=True),
            sb[sb.checkpoint == k][ip.FEATURES].reset_index(drop=True),
        )
    # sanity: checkpoints after the change do differ
    assert not np.allclose(sa[sa.checkpoint == 12]["score"], sb[sb.checkpoint == 12]["score"])


def test_truncated_innings_are_excluded() -> None:
    short = toy_balls(overs=12)  # ended before 20 overs with all wickets intact => rain-shortened
    assert ip.build_samples(short, ctx()).empty


def test_all_out_before_checkpoint_is_skipped() -> None:
    b = toy_balls(overs=9)
    b.loc[b.index[-10:], "is_wicket"] = True  # 10 wickets by over 9
    s = ip.build_samples(b, ctx())
    assert (s["checkpoint"] < 9).all() and (s["wickets"] < 10).all()


def test_remaining_runs_wrapper_adds_current_score() -> None:
    X = pd.DataFrame({"score": [50.0, 80.0, 100.0, 120.0], "x": [1.0, 2.0, 3.0, 4.0]})
    y = X["score"] + 40  # always 40 more runs
    m = ip.RemainingRuns(ip.models()["linear_regression"]).fit(X, y)
    assert np.allclose(m.predict(X), y)


def test_folds_are_chronological() -> None:
    df = pd.DataFrame(
        {
            "tournament_id": list("AABBCCDD"),
            "match_date": pd.to_datetime(
                [
                    "2010-01-01",
                    "2010-01-02",
                    "2011-01-01",
                    "2011-01-02",
                    "2012-01-01",
                    "2012-01-02",
                    "2013-01-01",
                    "2013-01-02",
                ]
            ),
        }
    )
    folds = list(ip.tournament_folds(df, min_train=2))
    assert [f[0] for f in folds] == ["C", "D"]
    for _t, tr, te in folds:
        assert df.loc[tr, "match_date"].max() < df.loc[te, "match_date"].min()


@pytest.mark.skipif(
    not (ROOT / "data/features/innings_projection_samples.parquet").exists(), reason="not built"
)
def test_models_beat_run_rate_baseline_on_real_data() -> None:
    samples = pd.read_parquet(ROOT / "data/features/innings_projection_samples.parquet")
    pred, metrics = ip.evaluate(samples)
    m = metrics[metrics.scope == "all"].set_index(["format", "model"])["mae"]
    for fmt in ("ODI", "T20"):
        assert m[(fmt, "linear_regression")] < m[(fmt, "baseline_run_rate")]
    assert pred["y"].notna().all() and np.isfinite(pred[ip.MODEL_NAMES].to_numpy()).all()
