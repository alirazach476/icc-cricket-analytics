# ruff: noqa: E501
"""Model 2: first-innings final-score projection from information available *during* the innings.

Each sample is one first innings observed at a checkpoint over k (after k overs). Features use only balls
bowled up to that checkpoint, plus pre-match context (team strength, venue history) from the leakage-safe
feature table. Target: the innings' final total.

Evaluation is time-aware: an expanding window over tournaments *of the same format* (train on earlier
editions, test on the next). Baseline: the textbook extrapolation "current score + current run rate x overs
left", which a model must beat to be worth having. Samples from the same innings are correlated, so the
bootstrap resamples whole innings.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
MAX_OVERS = {"ODI": 50, "T20": 20}
CHECKPOINTS = {"T20": [4, 6, 8, 10, 12, 14, 16, 18], "ODI": [10, 15, 20, 25, 30, 35, 40, 45]}
CONTEXT = ["bat_elo_diff", "venue_avg_first_innings", "bat_runs_for", "bowl_runs_against"]
LIVE = [
    "score",
    "wickets",
    "overs",
    "run_rate",
    "recent_run_rate",
    "wickets_last5",
    "boundary_freq",
    "dot_freq",
]
FEATURES = LIVE + ["projected_linear"] + CONTEXT
DB = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "cricket_gold.duckdb"


def load_first_innings_balls(db: Path = DB) -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(
            "select d.match_id, d.tournament_id, d.format, d.match_date, d.over_number, d.total_runs, "
            "d.is_wicket, d.is_legal_ball, d.is_boundary, d.is_dot_ball, m.is_dls "
            "from gold.fact_deliveries d join gold.fact_matches m using (match_id) "
            "where d.innings_number = 1 and not d.is_super_over and not m.is_dls"
        ).fetchdf()
    finally:
        con.close()


def build_samples(balls: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """One row per (innings, checkpoint over). Final totals use complete innings only."""
    ctx = features.set_index("match_id")[CONTEXT]
    rows = []
    for (mid, fmt), g in balls.groupby(["match_id", "format"], sort=False):
        n_over = MAX_OVERS[fmt]
        total, wickets_total = float(g["total_runs"].sum()), int(g["is_wicket"].sum())
        last_over = int(g["over_number"].max())
        complete = wickets_total >= 10 or last_over >= n_over
        if not complete or mid not in ctx.index:
            continue  # rain-shortened / truncated innings have no comparable final total
        per_over = g.groupby("over_number").agg(
            runs=("total_runs", "sum"),
            wk=("is_wicket", "sum"),
            balls=("is_legal_ball", "sum"),
            bound=("is_boundary", "sum"),
            dots=("is_dot_ball", "sum"),
        )
        first = g.iloc[0]
        for k in CHECKPOINTS[fmt]:
            upto = per_over.loc[per_over.index <= k]
            if len(upto) < k or last_over <= k:  # innings ended before this checkpoint
                continue
            score, wk = float(upto["runs"].sum()), int(upto["wk"].sum())
            if wk >= 10:
                continue
            recent = upto.iloc[-5:]
            balls_n = max(float(upto["balls"].sum()), 1.0)
            rr = score / k
            rows.append(
                {
                    "match_id": mid,
                    "tournament_id": first["tournament_id"],
                    "format": fmt,
                    "match_date": first["match_date"],
                    "checkpoint": k,
                    "score": score,
                    "wickets": wk,
                    "overs": float(k),
                    "run_rate": rr,
                    "recent_run_rate": float(recent["runs"].sum() / len(recent)),
                    "wickets_last5": int(recent["wk"].sum()),
                    "boundary_freq": float(upto["bound"].sum() / balls_n),
                    "dot_freq": float(upto["dots"].sum() / balls_n),
                    "projected_linear": score + rr * (n_over - k),
                    **ctx.loc[mid].to_dict(),
                    "y": total,
                }
            )
    return pd.DataFrame(rows)


MODEL_NAMES = [
    n
    for m in ("linear_regression", "random_forest", "gradient_boosting")
    for n in (m, f"{m}__remaining")
]


def models() -> dict:
    return {
        "linear_regression": make_pipeline(StandardScaler(), LinearRegression()),
        "random_forest": RandomForestRegressor(
            n_estimators=200, min_samples_leaf=8, max_features=0.6, random_state=SEED, n_jobs=1
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=SEED
        ),
    }


def tournament_folds(df: pd.DataFrame, min_train: int = 2):
    start = df.groupby("tournament_id")["match_date"].min().sort_values()
    order = list(start.index)
    for i, t in enumerate(order):
        if i < min_train:
            continue
        past = [p for p in order[:i] if start[p] < start[t]]
        tr, te = df.index[df["tournament_id"].isin(past)], df.index[df["tournament_id"] == t]
        if len(tr) and len(te):
            yield t, tr, te


def evaluate(samples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (pooled predictions, metrics by format x checkpoint x model)."""
    preds = []
    for _fmt, df in samples.groupby("format"):
        df = df.sort_values(["match_date", "match_id", "checkpoint"]).reset_index(drop=True)
        for _t, tr, te in tournament_folds(df):
            piece = df.loc[te, ["match_id", "tournament_id", "format", "checkpoint", "y"]].copy()
            piece["baseline_run_rate"] = df.loc[te, "projected_linear"].to_numpy()
            for name, model in models().items():
                model.fit(df.loc[tr, FEATURES], df.loc[tr, "y"])
                piece[name] = model.predict(df.loc[te, FEATURES])
                # Same learner, but predicting the runs still to come and adding the current score.
                rem = clone(model).fit(df.loc[tr, FEATURES], df.loc[tr, "y"] - df.loc[tr, "score"])
                piece[f"{name}__remaining"] = df.loc[te, "score"].to_numpy() + rem.predict(
                    df.loc[te, FEATURES]
                )
            preds.append(piece)
    pred = pd.concat(preds, ignore_index=True)
    rows = []
    for fmt, g in pred.groupby("format"):
        for scope, gg in [("all", g)] + [(f"over {c}", s) for c, s in g.groupby("checkpoint")]:
            for name in ["baseline_run_rate", *MODEL_NAMES]:
                err = gg["y"] - gg[name]
                rows.append(
                    {
                        "format": fmt,
                        "scope": scope,
                        "model": name,
                        "n": len(gg),
                        "mae": float(err.abs().mean()),
                        "rmse": float(np.sqrt((err**2).mean())),
                        "r2": float(1 - (err**2).sum() / ((gg["y"] - gg["y"].mean()) ** 2).sum()),
                    }
                )
    return pred, pd.DataFrame(rows)


def bootstrap_gain(
    pred: pd.DataFrame,
    model: str,
    baseline: str = "baseline_run_rate",
    n: int = 3000,
    seed: int = SEED,
):
    """95% interval of MAE(baseline) - MAE(model), resampling whole innings (positive = model better)."""
    rng = np.random.default_rng(seed)
    d = (pred["y"] - pred[baseline]).abs() - (pred["y"] - pred[model]).abs()
    per = d.groupby(pred["match_id"]).mean().to_numpy()
    boots = per[rng.integers(0, len(per), (n, len(per)))].mean(axis=1)
    return float(per.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


class RemainingRuns(BaseEstimator, RegressorMixin):
    """Predict the runs still to come and add the current score (deployable wrapper)."""

    def __init__(self, base=None):
        self.base = base

    def fit(self, X, y):
        self.model_ = clone(self.base).fit(X, np.asarray(y) - X["score"].to_numpy())
        return self

    def predict(self, X):
        return X["score"].to_numpy() + self.model_.predict(X)


def FINAL_MODEL(fmt: str):  # noqa: N802 - chosen from the evaluation in reports/model_evaluation
    return RemainingRuns(models()["linear_regression"])


def fit_final(samples: pd.DataFrame, out_dir: Path) -> dict[str, str]:
    import joblib

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for fmt, df in samples.groupby("format"):
        m = FINAL_MODEL(fmt).fit(df[FEATURES], df["y"])
        joblib.dump(
            {"model": m, "features": FEATURES, "format": fmt},
            out_dir / f"innings_projection_{fmt}.joblib",
        )
        paths[fmt] = f"models/innings_projection_{fmt}.joblib"
    return paths
