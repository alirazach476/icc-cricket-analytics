# ruff: noqa: E501
"""Stage 13: model interpretability.

* Permutation importance is measured **out of time**: for every expanding-window fold the model is fit on
  earlier tournaments and each feature is shuffled in the *test* fold; importance = how much the score
  gets worse. This measures what generalises, not what the model memorised.
* SHAP values explain the saved logistic model (exact for linear models, in log-odds). They are additive:
  base value + sum of contributions = the model's log-odds, which the tests verify.
* Features are correlated (Elo, win rate and form all measure team strength), so credit is shared between
  them; importance is therefore also reported by feature *family*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import log_loss, mean_absolute_error

from src.features.match_features import FEATURES_SCORE, FEATURES_WINNER
from src.ml.train import expanding_folds, score_models, winner_models

FAMILIES = {
    "team strength": [
        "elo_diff",
        "win_rate_diff",
        "form_diff",
        "runs_for_diff",
        "runs_against_diff",
        "min_prior_matches",
        "bat_runs_for",
        "bowl_runs_against",
        "bat_elo_diff",
    ],
    "head to head": ["h2h_rate_a"],
    "venue": ["venue_avg_first_innings", "venue_prior_n"],
    "context": ["is_knockout", "is_t20", "year", "format_avg_first_innings"],
    "toss": ["toss_edge_a", "toss_field"],
}


def family_of(feature: str) -> str:
    return next((f for f, cols in FAMILIES.items() if feature in cols), "other")


def _permute(X: pd.DataFrame, col: str, rng: np.random.Generator) -> pd.DataFrame:
    out = X.copy()
    out[col] = rng.permutation(out[col].to_numpy())
    return out


def permutation_importance_oot(
    feats: pd.DataFrame,
    task: str = "winner",
    model_name: str = "logistic",
    repeats: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Per-fold permutation importance on held-out future tournaments.

    winner: increase in log-loss; score: increase in MAE (both: bigger = more important)."""
    if task == "winner":
        df = (
            feats[feats["y_a_wins"].notna()]
            .sort_values(["match_date", "match_id"])
            .reset_index(drop=True)
        )
        cols, target, make = (
            FEATURES_WINNER,
            df["y_a_wins"].astype(int),
            winner_models()[model_name],
        )
    else:
        df = (
            feats[feats["y_first_innings_runs"].notna()]
            .sort_values(["match_date", "match_id"])
            .reset_index(drop=True)
        )
        cols, target, make = FEATURES_SCORE, df["y_first_innings_runs"], score_models()[model_name]
    rng = np.random.default_rng(seed)
    rows = []
    for t, tr, te in expanding_folds(df):
        model = clone(make)
        model.fit(df.loc[tr, cols], target[tr])
        X, y = df.loc[te, cols], target[te]
        base = _score(task, model, X, y)
        for c in cols:
            drops = [_score(task, model, _permute(X, c, rng), y) - base for _ in range(repeats)]
            rows.append({"fold": t, "feature": c, "importance": float(np.mean(drops))})
    long = pd.DataFrame(rows)
    out = (
        long.groupby("feature")["importance"]
        .agg(
            mean_importance="mean",
            std_across_folds="std",
            positive_folds=lambda s: int((s > 0).sum()),
        )
        .reset_index()
    )
    out["folds"] = long["fold"].nunique()
    out["family"] = out["feature"].map(family_of)
    return out.sort_values("mean_importance", ascending=False).reset_index(drop=True)


def _score(task: str, model, X: pd.DataFrame, y) -> float:
    if task == "winner":
        return float(
            log_loss(y, np.clip(model.predict_proba(X)[:, 1], 1e-6, 1 - 1e-6), labels=[0, 1])
        )
    return float(mean_absolute_error(y, model.predict(X)))


def family_importance(imp: pd.DataFrame) -> pd.DataFrame:
    g = imp.groupby("family")["mean_importance"].sum().sort_values(ascending=False).reset_index()
    g["share_of_positive"] = (
        g["mean_importance"].clip(lower=0) / g["mean_importance"].clip(lower=0).sum()
    )
    return g


# ------------------------------------------------------------------ SHAP (logistic model)
def fit_logistic(feats: pd.DataFrame):
    labelled = feats[feats["y_a_wins"].notna()].reset_index(drop=True)
    model = winner_models()["logistic"].fit(
        labelled[FEATURES_WINNER], labelled["y_a_wins"].astype(int)
    )
    return model, labelled


def shap_values(model, X: pd.DataFrame, background: pd.DataFrame):
    """Return (shap matrix in log-odds, base value) for the logistic pipeline."""
    import shap

    scaler, clf = model[0], model[-1]
    bg = scaler.transform(background[FEATURES_WINNER])
    explainer = shap.LinearExplainer(clf, shap.maskers.Independent(bg, max_samples=len(bg)))
    vals = explainer.shap_values(scaler.transform(X[FEATURES_WINNER]))
    return np.asarray(vals), float(np.ravel(explainer.expected_value)[0])


def global_shap(model, labelled: pd.DataFrame) -> pd.DataFrame:
    vals, _ = shap_values(model, labelled, labelled)
    out = pd.DataFrame(
        {
            "feature": FEATURES_WINNER,
            "mean_abs_shap": np.abs(vals).mean(axis=0),
            "mean_shap": vals.mean(axis=0),
        }
    )
    out["family"] = out["feature"].map(family_of)
    return out.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)


def explain_match(model, labelled: pd.DataFrame, match_id: str, top: int = 6) -> pd.DataFrame:
    """Contribution of each feature (log-odds) to the predicted win probability of team A."""
    row = labelled[labelled["match_id"] == match_id]
    if row.empty:
        raise KeyError(match_id)
    vals, base = shap_values(model, row, labelled)
    df = pd.DataFrame(
        {
            "feature": FEATURES_WINNER,
            "value": row[FEATURES_WINNER].iloc[0].to_numpy(),
            "shap_log_odds": vals[0],
        }
    )
    df["abs"] = df["shap_log_odds"].abs()
    df = df.sort_values("abs", ascending=False).drop(columns="abs")
    df.attrs["base_log_odds"] = base
    df.attrs["prob_team_a"] = float(model.predict_proba(row[FEATURES_WINNER])[0, 1])
    return df.head(top).reset_index(drop=True)


def feature_correlations(feats: pd.DataFrame) -> pd.DataFrame:
    return feats[FEATURES_WINNER].corr().round(2)


def dependence_on_elo(model, labelled: pd.DataFrame, points: int = 9) -> pd.DataFrame:
    """Predicted win probability of team A as Elo difference varies, other features at their median."""
    grid = np.linspace(-400, 400, points)
    base = labelled[FEATURES_WINNER].median().to_frame().T
    X = pd.concat([base] * points, ignore_index=True)
    X["elo_diff"] = grid
    return pd.DataFrame({"elo_diff": grid, "prob_team_a": model.predict_proba(X)[:, 1]})


ABLATION_SETS = {
    "elo_diff only": ["elo_diff"],
    "elo + runs for/against": ["elo_diff", "runs_for_diff", "runs_against_diff"],
    "team strength family": FAMILIES["team strength"][:6],
    "no toss, no venue": [
        c
        for c in FEATURES_WINNER
        if c not in ("toss_edge_a", "toss_field", "venue_avg_first_innings")
    ],
    "all features": FEATURES_WINNER,
}


def ablation(feats: pd.DataFrame) -> pd.DataFrame:
    """Out-of-time log-loss/accuracy of the logistic model using different feature sets.

    Answers "does this group of features *help*?", which permutation importance does not."""
    df = (
        feats[feats["y_a_wins"].notna()]
        .sort_values(["match_date", "match_id"])
        .reset_index(drop=True)
    )
    y = df["y_a_wins"].astype(int)
    rows = []
    for name, cols in ABLATION_SETS.items():
        preds = np.full(len(df), np.nan)
        for _t, tr, te in expanding_folds(df):
            m = clone(winner_models()["logistic"]).fit(df.loc[tr, cols], y[tr])
            preds[te] = m.predict_proba(df.loc[te, cols])[:, 1]
        ok = ~np.isnan(preds)
        p = np.clip(preds[ok], 1e-6, 1 - 1e-6)
        rows.append(
            {
                "feature_set": name,
                "n_features": len(cols),
                "n_test": int(ok.sum()),
                "log_loss": float(log_loss(y[ok], p)),
                "accuracy": float(((p > 0.5) == (y[ok] == 1)).mean()),
            }
        )
    return pd.DataFrame(rows)
