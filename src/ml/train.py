# ruff: noqa: E501
"""Stage 12: match-winner and first-innings-score models with time-respecting evaluation.

Evaluation protocol (this is what makes the numbers trustworthy):
* Expanding window over tournaments in chronological order: to score tournament T the model is fit
  only on tournaments that **started before T**, never on T or later. No random k-fold, which would
  let a model train on the future.
* Hyperparameters are fixed in advance (no tuning on the test folds).
* Every model is compared with honest baselines (a coin, an Elo-only predictor, the running format
  mean for scores). A model that cannot beat the baseline is reported as not beating it.
* Predictions of all test folds are pooled; accuracy gets a paired bootstrap interval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.features.match_features import (
    FEATURES_SCORE,
    FEATURES_SQUAD,
    FEATURES_WINNER,
    FEATURES_WINNER_EXT,
)

MIN_TRAIN_TOURNAMENTS = 5
SEED = 42


def winner_models() -> dict:
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000)),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=12, max_features="sqrt", random_state=SEED, n_jobs=1
        ),
        "grad_boosting": HistGradientBoostingClassifier(
            max_depth=2,
            learning_rate=0.05,
            max_iter=150,
            min_samples_leaf=20,
            l2_regularization=1.0,
            random_state=SEED,
        ),
        "xgboost": XGBClassifier(
            n_estimators=150,
            max_depth=2,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=5.0,
            min_child_weight=5,
            random_state=SEED,
            n_jobs=1,
            verbosity=0,
        ),
    }


def score_models() -> dict:
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "grad_boosting": HistGradientBoostingRegressor(
            max_depth=2,
            learning_rate=0.05,
            max_iter=150,
            min_samples_leaf=15,
            l2_regularization=1.0,
            random_state=SEED,
        ),
    }


def tournament_order(df: pd.DataFrame) -> list[str]:
    starts = df.groupby("tournament_id")["match_date"].min().sort_values()
    return list(starts.index)


def expanding_folds(df: pd.DataFrame, min_train: int = MIN_TRAIN_TOURNAMENTS):
    """Yield (test_tournament, train_index, test_index); train strictly precedes test in time."""
    order = tournament_order(df)
    start = df.groupby("tournament_id")["match_date"].min()
    for i, t in enumerate(order):
        if i < min_train:
            continue
        # Train only on tournaments that started before this one (guards against overlapping editions).
        past = [p for p in order[:i] if start[p] < start[t]]
        train = df.index[df["tournament_id"].isin(past)]
        test = df.index[df["tournament_id"] == t]
        if len(train) and len(test):
            yield t, train, test


def elo_probability(elo_diff: pd.Series) -> np.ndarray:
    return 1.0 / (1.0 + 10 ** (-np.asarray(elo_diff) / 400.0))


def classification_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "accuracy": float(((p > 0.5) == (y == 1)).mean()),
        "log_loss": float(log_loss(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else float("nan"),
        "precision": float(precision_score(y, p > 0.5, zero_division=0)),
        "recall": float(recall_score(y, p > 0.5, zero_division=0)),
        "f1": float(f1_score(y, p > 0.5, zero_division=0)),
    }


def paired_bootstrap(correct_a: np.ndarray, correct_b: np.ndarray, n: int = 4000, seed: int = SEED):
    """95% interval of accuracy(A) - accuracy(B), resampling matches (paired)."""
    rng = np.random.default_rng(seed)
    d = correct_a.astype(float) - correct_b.astype(float)
    idx = rng.integers(0, len(d), (n, len(d)))
    boots = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


@dataclass
class WinnerEval:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    comparisons: pd.DataFrame
    folds: int


def evaluate_winner(feats: pd.DataFrame) -> WinnerEval:
    df = (
        feats[feats["y_a_wins"].notna()]
        .sort_values(["match_date", "match_id"])
        .reset_index(drop=True)
    )
    X, y = df[FEATURES_WINNER], df["y_a_wins"].astype(int)
    has_squad = set(FEATURES_SQUAD) <= set(df.columns)
    pieces = []
    n_folds = 0
    for _t, tr, te in expanding_folds(df):
        n_folds += 1
        piece = df.loc[te, ["match_id", "tournament_id", "format", "match_date"]].copy()
        piece["y"] = y[te].to_numpy()
        piece["coin"] = 0.5
        piece["elo_only"] = elo_probability(df.loc[te, "elo_diff"])
        for name, model in winner_models().items():
            model.fit(X.loc[tr], y[tr])
            piece[name] = model.predict_proba(X.loc[te])[:, 1]
        # Squad-aware variant: adds career batting/bowling averages and experience of each XI.
        if has_squad:
            lm = clone(winner_models()["logistic"]).fit(df.loc[tr, FEATURES_WINNER_EXT], y[tr])
            piece["logistic_squad"] = lm.predict_proba(df.loc[te, FEATURES_WINNER_EXT])[:, 1]
        # Separate ODI and T20 pipelines: each format's model sees only that format's history.
        for fmt in ("ODI", "T20"):
            tr_f, te_f = tr[df.loc[tr, "format"] == fmt], te[df.loc[te, "format"] == fmt]
            if len(tr_f) < 30 or len(te_f) == 0:
                continue
            for name in ("logistic", "random_forest"):
                mf = clone(winner_models()[name]).fit(X.loc[tr_f], y[tr_f])
                piece.loc[te_f, f"{name}_by_format"] = mf.predict_proba(X.loc[te_f])[:, 1]
        pieces.append(piece)
    pred = pd.concat(pieces, ignore_index=True)
    extra = [
        c for c in ("logistic_squad", "logistic_by_format", "random_forest_by_format") if c in pred
    ]
    models = ["coin", "elo_only", *winner_models(), *extra]
    rows = []
    for scope, g in [("all", pred)] + [(f, s) for f, s in pred.groupby("format")]:
        for name in models:
            rows.append(
                {
                    "scope": scope,
                    "model": name,
                    "n": int(g[name].notna().sum()),
                    **classification_metrics(
                        g.loc[g[name].notna(), "y"].to_numpy(),
                        g.loc[g[name].notna(), name].to_numpy(),
                    ),
                }
            )
    metrics = pd.DataFrame(rows)
    comps = []
    for name in models:
        if name == "elo_only":
            continue
        d, lo, hi = paired_bootstrap(
            ((pred[name] > 0.5) == (pred["y"] == 1)).to_numpy(),
            ((pred["elo_only"] > 0.5) == (pred["y"] == 1)).to_numpy(),
        )
        comps.append(
            {
                "model": name,
                "accuracy_minus_elo": d,
                "ci_low": lo,
                "ci_high": hi,
                "beats_elo_significantly": lo > 0,
            }
        )
    return WinnerEval(pred, metrics, pd.DataFrame(comps), n_folds)


def paired_mae_bootstrap(
    pred: pd.DataFrame, model: str, baseline: str, n: int = 4000, seed: int = SEED
):
    """95% interval of MAE(baseline) - MAE(model): positive means the model has lower error."""
    d = ((pred["y"] - pred[baseline]).abs() - (pred["y"] - pred[model]).abs()).to_numpy()
    rng = np.random.default_rng(seed)
    boots = d[rng.integers(0, len(d), (n, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


@dataclass
class ScoreEval:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    folds: int


def evaluate_score(feats: pd.DataFrame) -> ScoreEval:
    df = (
        feats[feats["y_first_innings_runs"].notna()]
        .sort_values(["match_date", "match_id"])
        .reset_index(drop=True)
    )
    X, y = df[FEATURES_SCORE], df["y_first_innings_runs"]
    pieces, n_folds = [], 0
    for _t, tr, te in expanding_folds(df):
        n_folds += 1
        piece = df.loc[te, ["match_id", "tournament_id", "format", "match_date"]].copy()
        piece["y"] = y[te].to_numpy()
        piece["baseline_format_mean"] = df.loc[te, "format_avg_first_innings"].to_numpy()
        piece["baseline_venue_mean"] = df.loc[te, "venue_avg_first_innings"].to_numpy()
        for name, model in score_models().items():
            model.fit(X.loc[tr], y[tr])
            piece[name] = model.predict(X.loc[te])
        pieces.append(piece)
    pred = pd.concat(pieces, ignore_index=True)
    rows = []
    for scope, g in [("all", pred)] + [(f, s) for f, s in pred.groupby("format")]:
        for name in ["baseline_format_mean", "baseline_venue_mean", *score_models()]:
            err = g["y"] - g[name]
            rows.append(
                {
                    "scope": scope,
                    "model": name,
                    "n": len(g),
                    "mae": float(err.abs().mean()),
                    "rmse": float(np.sqrt((err**2).mean())),
                    "r2": float(1 - (err**2).sum() / ((g["y"] - g["y"].mean()) ** 2).sum()),
                }
            )
    return ScoreEval(pred, pd.DataFrame(rows), n_folds)


def calibration_table(pred: pd.DataFrame, model: str, bins: int = 5) -> pd.DataFrame:
    g = pred.assign(bin=pd.qcut(pred[model], bins, duplicates="drop"))
    return (
        g.groupby("bin", observed=True)
        .agg(n=("y", "size"), mean_predicted=(model, "mean"), actual_rate=("y", "mean"))
        .reset_index(drop=True)
    )


def fit_final(feats: pd.DataFrame, out_dir: Path) -> dict[str, str]:
    """Fit on every labelled match and save (for the dashboard / later prediction)."""
    import joblib

    out_dir.mkdir(parents=True, exist_ok=True)
    w = feats[feats["y_a_wins"].notna()]
    s = feats[feats["y_first_innings_runs"].notna()]
    paths = {}
    clf = winner_models()["logistic"].fit(w[FEATURES_WINNER], w["y_a_wins"].astype(int))
    joblib.dump({"model": clf, "features": FEATURES_WINNER}, out_dir / "winner_logistic.joblib")
    paths["winner_logistic"] = "models/winner_logistic.joblib"
    # Parsimonious model: the Stage 13 ablation found the Elo gap alone is as good as all features.
    elo = winner_models()["logistic"].fit(w[["elo_diff"]], w["y_a_wins"].astype(int))
    joblib.dump({"model": elo, "features": ["elo_diff"]}, out_dir / "winner_elo_logistic.joblib")
    paths["winner_elo_logistic"] = "models/winner_elo_logistic.joblib"
    reg = score_models()["ridge"].fit(s[FEATURES_SCORE], s["y_first_innings_runs"])
    joblib.dump({"model": reg, "features": FEATURES_SCORE}, out_dir / "score_ridge.joblib")
    paths["score_ridge"] = "models/score_ridge.joblib"
    coefs = pd.Series(clf[-1].coef_[0], index=FEATURES_WINNER).sort_values(key=abs, ascending=False)
    (out_dir / "winner_logistic_coefficients.json").write_text(
        json.dumps(coefs.round(4).to_dict(), indent=2), encoding="utf-8"
    )
    return paths


def calibration_curves(pred: pd.DataFrame, models: list[str], bins: int = 5) -> pd.DataFrame:
    """Binned predicted vs observed win rate for each model (the data behind a calibration curve)."""
    rows = []
    for name in models:
        g = pred[pred[name].notna()]
        b = pd.qcut(g[name], bins, duplicates="drop")
        t = g.groupby(b, observed=True).agg(
            n=("y", "size"), mean_predicted=(name, "mean"), observed_rate=("y", "mean")
        )
        t.insert(0, "model", name)
        rows.append(t.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)
