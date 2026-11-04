# ruff: noqa: E501
"""Stage 12: evaluation protocol is time-respecting, a leak detector stays at chance, models persist."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.features.match_features import FEATURES_SCORE, FEATURES_WINNER
from src.ml import train

ROOT = Path(__file__).resolve().parents[1]
FEATS = ROOT / "data" / "features" / "match_features.parquet"
needs_feats = pytest.mark.skipif(not FEATS.exists(), reason="features not built")


def toy() -> pd.DataFrame:
    rows = []
    for t in range(9):
        for k in range(6):
            rows.append(
                {
                    "match_id": f"{t}_{k}",
                    "tournament_id": f"T{t}",
                    "match_date": pd.Timestamp("2010-01-01") + pd.Timedelta(days=30 * t + k),
                }
            )
    return pd.DataFrame(rows)


def test_folds_train_strictly_before_test() -> None:
    df = toy()
    folds = list(train.expanding_folds(df, min_train=5))
    assert [f[0] for f in folds] == ["T5", "T6", "T7", "T8"]
    for _t, tr, te in folds:
        assert df.loc[tr, "match_date"].max() < df.loc[te, "match_date"].min()
        assert not set(tr) & set(te)


def test_overlapping_editions_are_not_used_for_training() -> None:
    df = toy()
    df.loc[df["tournament_id"] == "T6", "match_date"] = df.loc[
        df["tournament_id"] == "T5", "match_date"
    ].to_numpy()
    for t, tr, _te in train.expanding_folds(df, min_train=5):
        if t == "T6":
            assert "T5" not in set(df.loc[tr, "tournament_id"])  # same start date: not "earlier"


def test_elo_probability_and_metrics() -> None:
    assert train.elo_probability(pd.Series([0.0]))[0] == pytest.approx(0.5)
    assert train.elo_probability(pd.Series([400.0]))[0] == pytest.approx(10 / 11)
    m = train.classification_metrics(np.array([1, 0, 1, 0]), np.array([0.9, 0.1, 0.8, 0.3]))
    assert m["accuracy"] == 1.0 and m["auc"] == 1.0 and m["log_loss"] < 0.3


def test_paired_bootstrap_detects_a_real_difference() -> None:
    a, b = np.ones(300, dtype=bool), np.zeros(300, dtype=bool)
    d, lo, hi = train.paired_bootstrap(a, b)
    assert d == 1.0 and lo == 1.0
    rng = np.random.default_rng(1)
    same = rng.random(300) < 0.5
    _, lo, hi = train.paired_bootstrap(same, same)
    assert lo == hi == 0.0


@needs_feats
def test_label_shuffle_leak_detector() -> None:
    """With the labels randomly permuted no honest pipeline can beat chance. If this fails the
    evaluation (or the features) leaks information from the test fold."""
    feats = pd.read_parquet(FEATS)
    lab = feats["y_a_wins"].notna()
    shuffled = feats.copy()
    shuffled.loc[lab, "y_a_wins"] = np.random.default_rng(0).permutation(
        feats.loc[lab, "y_a_wins"].to_numpy()
    )
    res = train.evaluate_winner(shuffled)
    acc = res.metrics[(res.metrics.scope == "all") & (res.metrics.model != "coin")].set_index(
        "model"
    )["accuracy"]
    assert (acc.between(0.40, 0.60)).all(), acc.to_dict()
    real = train.evaluate_winner(feats).metrics
    real_acc = real[(real.scope == "all") & (real.model == "logistic")]["accuracy"].iloc[0]
    assert real_acc > acc["logistic"] + 0.05


@needs_feats
def test_models_beat_a_coin_and_probabilities_are_valid() -> None:
    feats = pd.read_parquet(FEATS)
    res = train.evaluate_winner(feats)
    assert res.folds >= 8
    for name in ("elo_only", "logistic", "random_forest", "grad_boosting"):
        assert res.predictions[name].between(0, 1).all()
    m = res.metrics[res.metrics.scope == "all"].set_index("model")
    assert m.loc["logistic", "log_loss"] < m.loc["coin", "log_loss"]
    assert m.loc["logistic", "accuracy"] > 0.55


@needs_feats
def test_score_model_has_baselines_and_finite_errors() -> None:
    res = train.evaluate_score(pd.read_parquet(FEATS))
    m = res.metrics[res.metrics.scope == "all"].set_index("model")
    assert {"baseline_format_mean", "baseline_venue_mean", "ridge", "grad_boosting"} <= set(m.index)
    assert np.isfinite(m[["mae", "rmse"]].to_numpy()).all()
    assert m.loc["ridge", "mae"] < m.loc["baseline_format_mean", "mae"]


@needs_feats
def test_final_models_persist_and_predict(tmp_path: Path) -> None:
    import joblib

    feats = pd.read_parquet(FEATS)
    train.fit_final(feats, tmp_path)
    w = joblib.load(tmp_path / "winner_logistic.joblib")
    p = w["model"].predict_proba(feats[w["features"]].head(5))[:, 1]
    assert ((p > 0) & (p < 1)).all() and w["features"] == FEATURES_WINNER
    s = joblib.load(tmp_path / "score_ridge.joblib")
    assert np.isfinite(s["model"].predict(feats[FEATURES_SCORE].head(5))).all()
