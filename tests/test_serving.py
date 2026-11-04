# ruff: noqa: E501
"""Serving layer: hypothetical-match features use only history; live projection matches training features."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.features.match_features import FEATURES_WINNER, load_matches, load_performances
from src.ml import innings_projection as ip
from src.ml import serving

ROOT = Path(__file__).resolve().parents[1]
needs = pytest.mark.skipif(
    not (ROOT / "models" / "winner_logistic.joblib").exists(), reason="models not built"
)


@pytest.fixture(scope="module")
def data():
    return load_matches(), load_performances()


@needs
def test_hypothetical_features_are_oriented_and_complete(data) -> None:
    m, p = data
    row = serving.hypothetical_features(m, p, "ODI", "espn_6", "espn_2")
    assert row["team_a_id"] == "espn_6" and row["team_b_id"] == "espn_2"
    assert row[FEATURES_WINNER].notna().all()


@needs
def test_swapping_teams_mirrors_the_features(data) -> None:
    m, p = data
    ab = serving.hypothetical_features(m, p, "ODI", "espn_6", "espn_2")
    ba = serving.hypothetical_features(m, p, "ODI", "espn_2", "espn_6")
    for f in ("elo_diff", "win_rate_diff", "form_diff", "runs_for_diff", "runs_against_diff"):
        assert ab[f] == pytest.approx(-ba[f])
    assert ab["h2h_rate_a"] == pytest.approx(1 - ba["h2h_rate_a"])
    assert 0 < serving.predict_winner(ab, "winner_logistic") < 1
    for model in ("winner_elo_logistic", "winner_logistic"):
        p_ab = serving.win_probability(m, p, "ODI", "espn_6", "espn_2", model)
        p_ba = serving.win_probability(m, p, "ODI", "espn_2", "espn_6", model)
        # swapping the teams must be exactly complementary
        assert p_ab + p_ba == pytest.approx(1.0, abs=1e-9), model


@needs
def test_hypothetical_uses_only_prior_history(data) -> None:
    """Dropping the most recent matches must change the hypothetical features: they depend on history."""
    m, p = data
    full = serving.hypothetical_features(m, p, "T20", "espn_6", "espn_2")
    early = m[m["match_date"] < pd.Timestamp("2016-01-01")]
    old = serving.hypothetical_features(early, p, "T20", "espn_6", "espn_2")
    assert full["elo_diff"] != old["elo_diff"]
    # and appending the hypothetical match does not alter any real match's features
    from src.features.match_features import build_match_features

    real = build_match_features(m, perf=p).set_index("match_id")
    again = build_match_features(
        pd.concat(
            [
                m,
                pd.DataFrame(
                    [
                        {
                            **m.iloc[0].to_dict(),
                            "match_id": "__x__",
                            "match_date": m["match_date"].max() + pd.Timedelta(days=5),
                            "winner_id": None,
                            "is_completed": False,
                        }
                    ]
                ),
            ]
        ),
        perf=p,
    ).set_index("match_id")
    cols = FEATURES_WINNER
    pd.testing.assert_frame_equal(real[cols], again.loc[real.index, cols])


@needs
def test_ordering_is_sensible_for_elo(data) -> None:
    m, p = data
    strong = serving.hypothetical_features(
        m, p, "ODI", "espn_6", "espn_8"
    )  # Australia v a weaker side
    assert strong["elo_a"] != strong["elo_b"]
    prob = serving.predict_winner(strong)
    assert (prob > 0.5) == (strong["elo_diff"] > 0)


def toy_first_innings(n_over=20) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    rows = []
    for o in range(1, n_over + 1):
        for _b in range(6):
            r = int(rng.integers(0, 7))
            rows.append(
                dict(
                    match_id="m",
                    tournament_id="T",
                    format="T20",
                    match_date=pd.Timestamp("2020-01-01"),
                    over_number=o,
                    total_runs=r,
                    is_wicket=bool(rng.random() < 0.04),
                    is_legal_ball=True,
                    is_boundary=r >= 4,
                    is_dot_ball=r == 0,
                    is_dls=False,
                )
            )
    return pd.DataFrame(rows)


def test_live_features_match_the_training_features() -> None:
    balls = toy_first_innings()
    balls["is_wicket"] = False  # keep the innings alive for all checkpoints
    ctx = {c: 0.0 for c in ip.CONTEXT}
    samples = ip.build_samples(
        balls, pd.DataFrame({"match_id": ["m"], **{c: [0.0] for c in ip.CONTEXT}})
    )
    for k in (6, 10, 14):
        live = serving.innings_features_at(balls, "T20", k, ctx)
        train = samples[samples.checkpoint == k].iloc[0]
        for f in ip.LIVE + ["projected_linear"]:
            assert live[f] == pytest.approx(train[f]), (k, f)


def test_live_features_ignore_later_balls() -> None:
    a = toy_first_innings()
    b = a.copy()
    b.loc[b.over_number > 8, "total_runs"] = 6
    ctx = {c: 0.0 for c in ip.CONTEXT}
    assert serving.innings_features_at(a, "T20", 8, ctx) == serving.innings_features_at(
        b, "T20", 8, ctx
    )
    assert serving.innings_features_at(a, "T20", 25, ctx) is None


@needs
def test_projection_is_plausible_and_beats_nothing_silly() -> None:
    balls = toy_first_innings()
    balls["is_wicket"] = False
    ctx = {
        "bat_elo_diff": 0.0,
        "venue_avg_first_innings": 160.0,
        "bat_runs_for": 160.0,
        "bowl_runs_against": 160.0,
    }
    f = serving.innings_features_at(balls, "T20", 10, ctx)
    out = serving.project_innings(f, "T20")
    assert f["score"] < out["model"] < 400 and out["run_rate_baseline"] > f["score"]
