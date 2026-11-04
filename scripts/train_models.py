# ruff: noqa: E501
"""Stage 12: evaluate (expanding window) and save the models; writes reports/ml_report.md."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml.train import (  # noqa: E402
    calibration_curves,
    calibration_table,
    evaluate_score,
    evaluate_winner,
    fit_final,
    paired_mae_bootstrap,
)


def md(df: pd.DataFrame, nd: int = 3) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append(
            "| " + " | ".join(f"{v:.{nd}f}" if isinstance(v, float) else str(v) for v in r) + " |"
        )
    return "\n".join(out)


def main() -> int:
    feats = pd.read_parquet(ROOT / "data" / "features" / "match_features.parquet")
    w, s = evaluate_winner(feats), evaluate_score(feats)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    meval = reports / "model_evaluation"
    meval.mkdir(exist_ok=True)
    cal_models = [m for m in ("elo_only", "logistic", "random_forest", "logistic_squad", "logistic_by_format") if m in w.predictions]
    cal = calibration_curves(w.predictions, cal_models)
    cal.to_csv(meval / "winner_calibration_curves.csv", index=False)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    for name, g in cal.groupby("model"):
        ax.plot(g["mean_predicted"], g["observed_rate"], "o-", label=name)
    ax.set_xlabel("predicted probability team A wins")
    ax.set_ylabel("observed rate")
    ax.set_title("Calibration (out-of-time folds)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(meval / "winner_calibration.png", dpi=130)
    plt.close(fig)
    w.comparisons.to_csv(meval / "winner_comparisons.csv", index=False)
    cmp_dir = reports / "model_comparison"
    cmp_dir.mkdir(exist_ok=True)
    w.metrics.to_csv(cmp_dir / "winner_metrics.csv", index=False)
    s.metrics.to_csv(cmp_dir / "score_metrics.csv", index=False)
    w.predictions.to_csv(meval / "winner_predictions.csv", index=False)
    comp_rows = []
    for scope, g in [("all", s.predictions)] + list(s.predictions.groupby("format")):
        for model in ("ridge", "grad_boosting"):
            for base in ("baseline_format_mean", "baseline_venue_mean"):
                d, lo, hi = paired_mae_bootstrap(g, model, base)
                comp_rows.append(
                    {
                        "scope": scope,
                        "model": model,
                        "vs": base,
                        "mae_gain": d,
                        "ci_low": lo,
                        "ci_high": hi,
                        "better_significantly": lo > 0,
                    }
                )
    score_cmp = pd.DataFrame(comp_rows)
    paths = fit_final(feats, ROOT / "models")

    wa = w.metrics[w.metrics.scope == "all"].drop(columns="scope")
    best = wa[~wa.model.isin(["coin"])].sort_values("log_loss").iloc[0]
    sa = s.metrics[s.metrics.scope == "all"].drop(columns="scope")
    cal = calibration_table(w.predictions, str(best.model))
    lines = [
        "# Machine-learning results (Stage 12)",
        "",
        "## Protocol",
        "",
        f"* Expanding window over tournaments: {w.folds} test tournaments, each scored by a model fit only on tournaments that started earlier (first {5} tournaments are training-only).",
        "* Features come from `src/features/match_features.py` (computed only from earlier matches; leakage tests in `tests/test_features.py`).",
        "* Hyperparameters fixed in advance; nothing tuned on test folds. Baselines: a coin, an Elo-only predictor, running format mean / venue mean for scores.",
        "",
        "## Who wins? (team A vs team B, decided matches only)",
        "",
        md(wa),
        "",
        "Accuracy difference against the Elo-only baseline (paired bootstrap, 95% interval):",
        "",
        md(w.comparisons),
        "",
        f"Calibration of the lowest-log-loss model (`{best.model}`): do predicted probabilities match what happened?",
        "",
        md(cal),
        "",
        "By format:",
        "",
        md(w.metrics[w.metrics.scope != "all"]),
        "",
        "## How many runs will the team batting first score?",
        "",
        "Lower MAE/RMSE is better; R2 is relative to predicting the test mean.",
        "",
        md(sa),
        "",
        "By format:",
        "",
        md(s.metrics[s.metrics.scope != "all"]),
        "",
        "Paired bootstrap of the error reduction (positive = model beats the baseline):",
        "",
        md(score_cmp),
        "",
        "Note: the pooled R2 is inflated because ODI and T20 scores differ by ~100 runs; read the per-format rows.",
        "",
        "## Saved models",
        "",
        *[f"* `{p}`" for p in paths.values()],
        "",
        "## Limits",
        "",
        "* About 640 decided matches in total: small data, so differences of a point or two in accuracy are noise (see the intervals).",
        "* Outcomes of a single cricket match are close to a coin flip even for strong models; the realistic goal is calibrated probabilities slightly better than Elo.",
        "* Team features are team-level only. Squad, pitch, weather and day/night are not modelled (not collected).",
        "",
    ]
    (reports / "ml_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(wa.round(3).to_string(index=False))
    print()
    print(w.comparisons.round(3).to_string(index=False))
    print()
    print(sa.round(2).to_string(index=False))
    print()
    print(s.metrics[s.metrics.scope != "all"].round(2).to_string(index=False))
    print()
    print(score_cmp.round(2).to_string(index=False))
    print()
    print(cal.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
