# ruff: noqa: E402, E501
"""Evaluate the match-winner models for the Champions Trophy and the Test Championship.

    python scripts/build_competition_features.py     # features and Elo ratings first
    python scripts/train_competition_models.py

Writes, per competition ``<code>`` (ct, wtc), to ``reports/model_evaluation/``:
``<code>_winner_metrics.csv``, ``<code>_winner_comparisons.csv``, ``<code>_winner_predictions.csv``,
``<code>_winner_calibration.csv`` and ``<code>_elo_model.json`` (slope for the win-probability calculator).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.ml.competition_models import CONFIG, calibration, evaluate, fit_elo_slope, load_features

OUT = ROOT / "reports" / "model_evaluation"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for code, cfg in CONFIG.items():
        feats = load_features(code)
        ev = evaluate(code, feats)
        ev.metrics.to_csv(OUT / f"{code}_winner_metrics.csv", index=False)
        ev.comparisons.to_csv(OUT / f"{code}_winner_comparisons.csv", index=False)
        ev.predictions.to_csv(OUT / f"{code}_winner_predictions.csv", index=False)
        cal = pd.concat([calibration(ev.predictions, m).assign(model=m) for m in ("elo_only", "elo_logistic", "logistic")], ignore_index=True)
        cal.to_csv(OUT / f"{code}_winner_calibration.csv", index=False)
        slope = fit_elo_slope(feats)
        (OUT / f"{code}_elo_model.json").write_text(
            json.dumps({"slope_per_elo_point": slope, "decided_matches": ev.n_labelled, "format": cfg["format"]}, indent=2),
            encoding="utf-8",
        )
        print(f"\n[{code}] {cfg['label']}: {ev.n_labelled} decided matches ({ev.n_unlabelled} draws/ties/abandoned have no label)")
        print(f"       scored editions: {', '.join(ev.folds)}  ({len(ev.predictions)} test matches)")
        show = ev.metrics[["model", "accuracy", "accuracy_low", "accuracy_high", "log_loss", "brier", "auc"]].round(3)
        print(show.to_string(index=False))
        c = ev.comparisons
        print(c[c["versus"] == "elo_only"].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
