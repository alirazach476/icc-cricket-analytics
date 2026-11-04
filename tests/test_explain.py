# ruff: noqa: E501
"""Stage 13: interpretability maths is correct (planted signal, SHAP additivity) and sane on real data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.features.match_features import FEATURES_WINNER
from src.ml import explain as ex

FEATS = Path(__file__).resolve().parents[1] / "data" / "features" / "match_features.parquet"
needs_feats = pytest.mark.skipif(not FEATS.exists(), reason="features not built")


def planted(n_tournaments: int = 9, per: int = 40, seed: int = 0) -> pd.DataFrame:
    """Only elo_diff drives the label; every other feature is pure noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(n_tournaments):
        for k in range(per):
            rows.append(
                {
                    "match_id": f"{t}_{k}",
                    "tournament_id": f"T{t}",
                    "match_date": pd.Timestamp("2010-01-01") + pd.Timedelta(days=60 * t + k // 3),
                    "format": "ODI",
                    **{c: rng.normal() for c in FEATURES_WINNER},
                }
            )
    df = pd.DataFrame(rows)
    df["elo_diff"] = df["elo_diff"] * 150
    df["y_a_wins"] = (rng.random(len(df)) < 1 / (1 + 10 ** (-df["elo_diff"] / 150))).astype(float)
    df["y_first_innings_runs"] = np.nan
    return df


def test_permutation_importance_finds_the_planted_feature() -> None:
    imp = ex.permutation_importance_oot(planted(), "winner", "logistic", repeats=5)
    top = imp.iloc[0]
    assert top["feature"] == "elo_diff" and top["positive_folds"] == top["folds"]
    noise = imp[imp["feature"] != "elo_diff"]["mean_importance"]
    # Noise features may wobble a little in small folds, but must be far below the real driver.
    assert noise.max() < 0.25 * top["mean_importance"], (noise.max(), top["mean_importance"])


def test_shap_is_additive_and_matches_model() -> None:
    df = planted()
    model, labelled = ex.fit_logistic(df)
    vals, base = ex.shap_values(model, labelled.head(25), labelled)
    clf, scaler = model[-1], model[0]
    logit = clf.decision_function(scaler.transform(labelled.head(25)[FEATURES_WINNER]))
    assert np.allclose(vals.sum(axis=1) + base, logit, atol=1e-6)
    top = ex.global_shap(model, labelled).iloc[0]["feature"]
    assert top == "elo_diff"


def test_explain_match_probability_and_errors() -> None:
    model, labelled = ex.fit_logistic(planted())
    e = ex.explain_match(model, labelled, "3_5")
    assert 0 < e.attrs["prob_team_a"] < 1 and len(e) == 6
    assert e["shap_log_odds"].abs().is_monotonic_decreasing
    with pytest.raises(KeyError):
        ex.explain_match(model, labelled, "nope")


def test_dependence_is_monotone_in_elo_for_planted_data() -> None:
    model, labelled = ex.fit_logistic(planted())
    dep = ex.dependence_on_elo(model, labelled)
    assert dep["prob_team_a"].is_monotonic_increasing and dep["prob_team_a"].between(0, 1).all()


def test_family_mapping_covers_every_feature() -> None:
    from src.features.match_features import FEATURES_SCORE

    assert all(ex.family_of(f) != "other" for f in FEATURES_WINNER + FEATURES_SCORE)
    imp = pd.DataFrame(
        {
            "feature": ["elo_diff", "h2h_rate_a"],
            "mean_importance": [0.3, 0.1],
            "family": ["team strength", "head to head"],
        }
    )
    assert ex.family_importance(imp)["share_of_positive"].sum() == pytest.approx(1.0)


@needs_feats
def test_real_data_sanity() -> None:
    feats = pd.read_parquet(FEATS)
    imp = ex.permutation_importance_oot(feats, "winner", "logistic", repeats=4)
    fam = ex.family_importance(imp)
    assert fam.iloc[0]["family"] == "team strength"
    abl = ex.ablation(feats).set_index("feature_set")
    assert (
        set(abl.index) == set(ex.ABLATION_SETS) and (abl["n_test"] == abl["n_test"].iloc[0]).all()
    )
    assert abl["accuracy"].min() > 0.55
    sc = ex.permutation_importance_oot(feats, "score", "ridge", repeats=4)
    assert sc.iloc[0]["feature"] == "bat_elo_diff"
