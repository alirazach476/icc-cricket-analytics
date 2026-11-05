# ruff: noqa: E402, E501
"""Data behind the extra machine-learning diagnostics on the dashboard (offline step; needs scikit-learn and shap).

* ``reports/model_evaluation/score_predictions.csv``: held-out pre-match first-innings score predictions (expanding window,
  same protocol as the World Cup score models) for actual-vs-predicted and residual charts;
* ``reports/shap_analysis/shap_values_winner.csv``: SHAP value of every feature for every labelled match (logistic winner
  model fitted on all labelled matches) with the feature values, for SHAP dependence plots.

    python scripts/build_ml_diagnostics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import shap

from src.features.match_features import FEATURES_WINNER
from src.ml.train import evaluate_score, winner_models


def main() -> None:
    feats = pd.read_parquet(ROOT / "data" / "features" / "match_features.parquet")

    ev = evaluate_score(feats)
    out = ROOT / "reports" / "model_evaluation" / "score_predictions.csv"
    ev.predictions.to_csv(out, index=False)
    print(f"score predictions: {len(ev.predictions)} held-out matches -> {out.relative_to(ROOT)}")

    lab = feats[feats["y_a_wins"].notna()].reset_index(drop=True)
    model = winner_models()["logistic"].fit(lab[FEATURES_WINNER], lab["y_a_wins"].astype(int))
    scaled = model[0].transform(lab[FEATURES_WINNER])
    values = shap.LinearExplainer(model[-1], scaled).shap_values(scaled)
    frame = lab[["match_id", "tournament_id", "format"]].copy()
    for i, f in enumerate(FEATURES_WINNER):
        frame[f] = lab[f].to_numpy()
        frame[f"shap_{f}"] = values[:, i]
    out = ROOT / "reports" / "shap_analysis" / "shap_values_winner.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.round(5).to_csv(out, index=False)
    print(f"SHAP values: {len(frame)} matches x {len(FEATURES_WINNER)} features -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
