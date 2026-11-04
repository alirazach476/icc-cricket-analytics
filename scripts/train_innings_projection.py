# ruff: noqa: E501
"""Model 2: evaluate the in-innings first-innings score projection -> reports/model_evaluation/."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import innings_projection as ip  # noqa: E402


def main() -> int:
    feats = pd.read_parquet(ROOT / "data" / "features" / "match_features.parquet")
    samples = ip.build_samples(ip.load_first_innings_balls(), feats)
    out = ROOT / "reports" / "model_evaluation"
    out.mkdir(parents=True, exist_ok=True)
    samples.to_parquet(
        ROOT / "data" / "features" / "innings_projection_samples.parquet", index=False
    )
    pred, metrics = ip.evaluate(samples)
    metrics.to_csv(out / "innings_projection_metrics.csv", index=False)
    pred.to_csv(out / "innings_projection_predictions.csv", index=False)
    gains = []
    for fmt, g in pred.groupby("format"):
        for model in ip.MODEL_NAMES:
            d, lo, hi = ip.bootstrap_gain(g.reset_index(drop=True), model)
            gains.append(
                {
                    "format": fmt,
                    "model": model,
                    "mae_gain_vs_run_rate": d,
                    "ci_low": lo,
                    "ci_high": hi,
                    "better_significantly": lo > 0,
                }
            )
    gains = pd.DataFrame(gains)
    gains.to_csv(out / "innings_projection_gains.csv", index=False)
    paths = ip.fit_final(samples, ROOT / "models")
    print(f"samples: {len(samples)} from {samples.match_id.nunique()} innings")
    print(metrics[metrics.scope == "all"].round(2).to_string(index=False))
    print(gains.round(2).to_string(index=False))
    print(
        metrics[
            (
                metrics.model.isin(
                    [
                        "baseline_run_rate",
                        "linear_regression__remaining",
                        "gradient_boosting__remaining",
                    ]
                )
            )
            & metrics.scope.str.startswith("over")
        ]
        .round(1)
        .to_string(index=False)
    )
    print(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
