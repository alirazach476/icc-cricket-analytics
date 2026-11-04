# ruff: noqa: E501
"""Prediction services used by the dashboard (and tested without it).

Hypothetical-match features are produced by appending a *future* match to the real history and running the
same leakage-safe builder, so a prediction uses exactly the logic the models were evaluated with: only
completed matches before the hypothetical date can influence it.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.features.match_features import build_match_features, team_a_is_team1
from src.ml import innings_projection as ip

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"


def _orientable_id(a_is_team1: bool = True) -> str:
    """A synthetic match id whose hashed orientation puts team1 as 'team A' (so outputs are not flipped)."""
    i = 0
    while team_a_is_team1(f"__hypothetical_{i}") != a_is_team1:
        i += 1
    return f"__hypothetical_{i}"


_HYPO_CACHE: dict[tuple, pd.Series] = {}


def hypothetical_features(
    matches: pd.DataFrame,
    perf: pd.DataFrame | None,
    fmt: str,
    team_a: str,
    team_b: str,
    venue_id: str | None = None,
    knockout: bool = False,
    bat_first: str | None = None,
    year: int | None = None,
) -> pd.Series:
    """Cached wrapper: rebuilding every historical feature takes seconds, and the same
    fixture is asked for repeatedly (interactive dashboard re-runs)."""
    key = (
        fmt, team_a, team_b, venue_id, bool(knockout), bat_first, year, len(matches),
        str(matches["match_date"].max()), None if perf is None else len(perf),
    )
    if key not in _HYPO_CACHE:
        if len(_HYPO_CACHE) > 256:
            _HYPO_CACHE.clear()
        _HYPO_CACHE[key] = _hypothetical_features(
            matches, perf, fmt, team_a, team_b, venue_id, knockout, bat_first, year
        )
    return _HYPO_CACHE[key].copy()


def _hypothetical_features(
    matches: pd.DataFrame,
    perf: pd.DataFrame | None,
    fmt: str,
    team_a: str,
    team_b: str,
    venue_id: str | None = None,
    knockout: bool = False,
    bat_first: str | None = None,
    year: int | None = None,
) -> pd.Series:
    """Feature row for team_a vs team_b played after every match in ``matches`` (nothing from the future)."""
    last = pd.Timestamp(matches["match_date"].max())
    mid = _orientable_id(True)
    row = {
        "match_id": mid,
        "tournament_id": "__hypothetical__",
        "format": fmt,
        "year": int(year or last.year),
        "match_date": last + pd.Timedelta(days=1),
        "is_knockout": bool(knockout),
        "venue_id": venue_id,
        "team1_id": team_a,
        "team2_id": team_b,
        "winner_id": None,
        "toss_winner_id": None,
        "toss_decision": None,
        "is_completed": False,
        "is_walkover": False,
        "is_tie": False,
        "is_dls": False,
        "batting_first_team_id": bat_first or team_a,
        "batting_second_team_id": team_b if (bat_first or team_a) == team_a else team_a,
        "first_innings_runs": np.nan,
        "second_innings_runs": np.nan,
    }
    frame = pd.concat([matches, pd.DataFrame([row])], ignore_index=True)
    feats = build_match_features(frame, perf=perf)
    out = feats[feats["match_id"] == mid].iloc[0]
    assert out["team_a_id"] == team_a
    return out


def load_model(name: str) -> dict:
    return joblib.load(MODELS / f"{name}.joblib")


def predict_winner(row: pd.Series, model: str = "winner_elo_logistic") -> float:
    """Probability that team A wins, using a saved model ('winner_elo_logistic' or 'winner_logistic')."""
    pack = load_model(model)
    X = pd.DataFrame([row[pack["features"]].astype(float)])
    return float(pack["model"].predict_proba(X)[0, 1])


def win_probability(
    matches: pd.DataFrame, perf: pd.DataFrame | None, fmt: str, team_a: str, team_b: str,
    model: str = "winner_elo_logistic", **kw,
) -> float:
    """P(team A beats team B), averaged over both orientations so swapping the teams gives 1 - p exactly.

    A model trained on randomly oriented pairs can carry small intercept/context terms that are not
    antisymmetric; averaging removes that artefact."""
    ab = predict_winner(hypothetical_features(matches, perf, fmt, team_a, team_b, **kw), model)
    kw_ba = {k: v for k, v in kw.items() if k != "bat_first"}
    ba = predict_winner(hypothetical_features(matches, perf, fmt, team_b, team_a, **kw_ba), model)
    return 0.5 * (ab + 1.0 - ba)


def predict_prematch_score(row: pd.Series) -> float:
    """Pre-match first-innings score of the side batting first (ridge model)."""
    pack = load_model("score_ridge")
    X = pd.DataFrame([row[pack["features"]].astype(float)])
    return float(pack["model"].predict(X)[0])


# --------------------------------------------------------------------------- live innings projection
def innings_features_at(
    balls: pd.DataFrame, fmt: str, over: int, ctx: dict[str, float]
) -> dict | None:
    """Features after ``over`` completed overs of a first innings. Uses only balls up to that over."""
    g = balls[balls["over_number"] <= over]
    per = g.groupby("over_number").agg(
        runs=("total_runs", "sum"),
        wk=("is_wicket", "sum"),
        balls=("is_legal_ball", "sum"),
        bound=("is_boundary", "sum"),
        dots=("is_dot_ball", "sum"),
    )
    if len(per) < over or over < 1:
        return None
    score, wk = float(per["runs"].sum()), int(per["wk"].sum())
    n_over = ip.MAX_OVERS[fmt]
    recent = per.iloc[-5:]
    nb = max(float(per["balls"].sum()), 1.0)
    rr = score / over
    return {
        "score": score,
        "wickets": wk,
        "overs": float(over),
        "run_rate": rr,
        "recent_run_rate": float(recent["runs"].sum() / len(recent)),
        "wickets_last5": int(recent["wk"].sum()),
        "boundary_freq": float(per["bound"].sum() / nb),
        "dot_freq": float(per["dots"].sum() / nb),
        "projected_linear": score + rr * (n_over - over),
        **ctx,
    }


def project_innings(feats: dict, fmt: str) -> dict[str, float]:
    """Projected final total from the saved live model, next to the run-rate extrapolation baseline."""
    pack = load_model(f"innings_projection_{fmt}")
    X = pd.DataFrame([{k: feats[k] for k in pack["features"]}])
    return {
        "model": float(pack["model"].predict(X)[0]),
        "run_rate_baseline": float(feats["projected_linear"]),
    }
