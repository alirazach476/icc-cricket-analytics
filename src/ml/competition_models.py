# ruff: noqa: E501
"""Match-winner models for the Champions Trophy (ODI) and the World Test Championship (Test).

Same protocol as the World Cup models (``src.ml.train``), scaled to much smaller samples:

* expanding window over editions in time order: an edition is only scored by a model fitted on editions that started
  before it (``MIN_TRAIN`` editions are always training-only);
* fixed hyperparameters, nothing tuned on test folds;
* honest baselines: a coin, and an Elo-only predictor;
* every accuracy comes with a bootstrap interval, because 50-160 test matches cannot support fine distinctions;
* only decided matches have a label: draws, ties, abandoned and no-result matches are not predicted.

Features are the leakage-safe table from ``scripts/build_competition_features.py`` (each match uses only earlier matches).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features.match_features import FEATURES_WINNER
from src.ml.train import (
    SEED,
    classification_metrics,
    elo_probability,
    expanding_folds,
    paired_bootstrap,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = {
    # code: (training-only editions before the first scored one, format name)
    "ct": {"min_train": 3, "format": "ODI", "label": "Champions Trophy"},
    "wtc": {"min_train": 1, "format": "Test", "label": "World Test Championship"},
}
MODELS = ["coin", "elo_only", "elo_logistic", "logistic", "random_forest"]


def models() -> dict:
    return {
        # the Elo gap alone, with the slope learned from earlier matches; no intercept, so team order cannot matter
        "elo_logistic": LogisticRegression(C=1.0, fit_intercept=False, max_iter=1000),
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000)),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=8, max_features="sqrt", random_state=SEED, n_jobs=1
        ),
    }


def load_features(code: str) -> pd.DataFrame:
    path = ROOT / "data" / "features" / f"{code}_match_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run scripts/build_competition_features.py first")
    return pd.read_parquet(path)


@dataclass
class CompetitionEval:
    code: str
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    comparisons: pd.DataFrame
    folds: list[str]
    n_labelled: int
    n_unlabelled: int


def accuracy_interval(correct: np.ndarray, n: int = 4000, seed: int = SEED) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(correct), (n, len(correct)))
    boots = correct[idx].mean(axis=1)
    return float(correct.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def evaluate(code: str, feats: pd.DataFrame | None = None) -> CompetitionEval:
    cfg = CONFIG[code]
    feats = load_features(code) if feats is None else feats
    labelled = (
        feats[feats["y_a_wins"].notna()].sort_values(["match_date", "match_id"]).reset_index(drop=True)
    )
    y = labelled["y_a_wins"].astype(int)
    pieces, folds = [], []
    for t, tr, te in expanding_folds(labelled, min_train=cfg["min_train"]):
        folds.append(t)
        piece = labelled.loc[te, ["match_id", "tournament_id", "format", "match_date"]].copy()
        piece["y"] = y[te].to_numpy()
        piece["coin"] = 0.5
        piece["elo_only"] = elo_probability(labelled.loc[te, "elo_diff"])
        piece["elo_diff"] = labelled.loc[te, "elo_diff"].to_numpy()
        for name, model in models().items():
            cols = ["elo_diff"] if name == "elo_logistic" else FEATURES_WINNER
            model.fit(labelled.loc[tr, cols], y[tr])
            piece[name] = model.predict_proba(labelled.loc[te, cols])[:, 1]
        pieces.append(piece)
    pred = pd.concat(pieces, ignore_index=True)

    rows, comps = [], []
    for name in MODELS:
        correct = ((pred[name] > 0.5) == (pred["y"] == 1)).to_numpy()
        acc, lo, hi = accuracy_interval(correct)
        rows.append({"model": name, "n": len(pred), **classification_metrics(pred["y"].to_numpy(), pred[name].to_numpy()), "accuracy_low": lo, "accuracy_high": hi})
        for base in ("coin", "elo_only"):
            if name == base:
                continue
            d, dlo, dhi = paired_bootstrap(correct, ((pred[base] > 0.5) == (pred["y"] == 1)).to_numpy())
            comps.append({"model": name, "versus": base, "accuracy_difference": d, "ci_low": dlo, "ci_high": dhi, "clearly_better": dlo > 0})
    return CompetitionEval(code, pred, pd.DataFrame(rows), pd.DataFrame(comps), folds, len(labelled), len(feats) - len(labelled))


def calibration(pred: pd.DataFrame, model: str, bins: int = 4) -> pd.DataFrame:
    g = pred.assign(bin=pd.qcut(pred[model], bins, duplicates="drop"))
    return (
        g.groupby("bin", observed=True)
        .agg(n=("y", "size"), mean_predicted=(model, "mean"), actual_rate=("y", "mean"))
        .reset_index(drop=True)
    )


def fit_elo_slope(feats: pd.DataFrame) -> float:
    """Slope of log-odds per Elo point, fitted on every decided match (used by the win-probability calculator)."""
    lab = feats[feats["y_a_wins"].notna()]
    m = LogisticRegression(C=1.0, fit_intercept=False, max_iter=1000).fit(lab[["elo_diff"]], lab["y_a_wins"].astype(int))
    return float(m.coef_[0][0])
