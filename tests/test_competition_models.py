"""Champions Trophy / Test Championship winner models: chronological, no leakage, honest intervals."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ml.competition_models import CONFIG, evaluate, load_features  # noqa: E402
from src.ml.train import expanding_folds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    not (ROOT / "data/features/wtc_match_features.parquet").exists(), reason="features not built"
)


@pytest.fixture(scope="module", params=sorted(CONFIG))
def ev(request):
    return evaluate(request.param)


def test_every_scored_edition_is_predicted_from_earlier_editions_only(ev) -> None:
    feats = load_features(ev.code)
    lab = feats[feats["y_a_wins"].notna()].sort_values(["match_date", "match_id"]).reset_index(drop=True)
    seen = 0
    for _t, tr, te in expanding_folds(lab, min_train=CONFIG[ev.code]["min_train"]):
        assert lab.loc[tr, "match_date"].max() < lab.loc[te, "match_date"].min()
        seen += len(te)
    assert seen == len(ev.predictions) > 40
    assert len(ev.folds) >= 2


def test_only_decided_matches_are_labelled(ev) -> None:
    feats = load_features(ev.code)
    assert ev.n_labelled + ev.n_unlabelled == len(feats)
    if ev.code == "wtc":
        assert ev.n_unlabelled == 29  # the draws


def test_metrics_are_consistent_and_intervals_bracket_the_estimate(ev) -> None:
    m = ev.metrics.set_index("model")
    assert (m["n"] == len(ev.predictions)).all()
    assert (m["accuracy_low"] <= m["accuracy"]).all() and (m["accuracy"] <= m["accuracy_high"]).all()
    assert ev.predictions[["elo_only", "elo_logistic", "logistic", "random_forest"]].apply(lambda c: c.between(0, 1).all()).all()
    assert abs(m.loc["coin", "log_loss"] - np.log(2)) < 1e-9


def test_label_shuffle_gives_chance_level(ev) -> None:
    """If the outcomes are shuffled, no model may look good (a leak would show up here)."""
    feats = load_features(ev.code).copy()
    rng = np.random.default_rng(7)
    mask = feats["y_a_wins"].notna()
    feats.loc[mask, "y_a_wins"] = rng.permutation(feats.loc[mask, "y_a_wins"].to_numpy())
    shuffled = evaluate(ev.code, feats).metrics.set_index("model")
    for model in ("elo_only", "logistic", "random_forest"):
        assert shuffled.loc[model, "accuracy_low"] <= 0.55 <= shuffled.loc[model, "accuracy_high"] + 0.1, model


def test_test_championship_elo_beats_a_coin_and_ratings_are_conserved() -> None:
    m = evaluate("wtc").metrics.set_index("model")
    assert m.loc["elo_only", "accuracy_low"] > 0.5
    r = pd.read_csv(ROOT / "reports/model_evaluation/wtc_elo_ratings.csv")
    assert abs(r["elo"].sum() - 1500.0 * len(r)) < 0.5
    assert json.loads((ROOT / "reports/model_evaluation/wtc_elo_model.json").read_text())["slope_per_elo_point"] > 0
