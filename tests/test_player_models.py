# ruff: noqa: E501
"""Models 3-5: consistency maths, clustering recovers planted structure, regression signs, minimum samples."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from src.ml import player_models as pm

ROOT = Path(__file__).resolve().parents[1]


def perf_frame(players: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    for pid, runs in players.items():
        for i, r in enumerate(runs):
            rows.append(
                dict(
                    player_id=pid,
                    full_name=pid.title(),
                    match_id=f"{pid}{i}",
                    did_bat=True,
                    did_bowl=False,
                    runs=r,
                    balls_faced=max(int(r), 1),
                    fours=0,
                    sixes=0,
                    batting_position=3,
                    is_out=True,
                    format="ODI",
                    balls_bowled=np.nan,
                    runs_conceded=np.nan,
                    wickets=np.nan,
                )
            )
    return pd.DataFrame(rows)


def test_consistency_values_and_minimum_sample() -> None:
    p = perf_frame(
        {
            "steady": [30.0] * 12,
            "streaky": [0, 90, 0, 80, 0, 70, 0, 60, 0, 50, 0, 40],
            "few": [50.0] * 4,
        }
    )
    c = pm.batting_consistency(p).set_index("player")
    assert "Few" not in c.index  # below the minimum number of innings
    assert c.loc["Steady", "cv"] == pytest.approx(0.0, abs=1e-9) and c.loc["Streaky", "cv"] > 1.0
    assert c.loc["Steady", "median_runs"] == 30 and c.loc["Steady", "pct_30_plus"] == 1.0
    assert (c["mean_ci_low"] <= c["mean_runs"]).all() and (
        c["mean_runs"] <= c["mean_ci_high"]
    ).all()


def planted_clusters(seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    centers = {0: (0, 0, 0), 1: (6, 6, 0), 2: (0, 6, 6)}
    rows = [
        dict(
            player=f"p{c}_{i}",
            **{f"f{j}": centers[c][j] + rng.normal(0, 0.5) for j in range(3)},
            true=c,
        )
        for c in centers
        for i in range(40)
    ]
    return pd.DataFrame(rows)


def test_clustering_recovers_planted_groups_and_is_stable() -> None:
    df = planted_clusters()
    res = pm.cluster_players(df, ["f0", "f1", "f2"], n_boot=20)
    assert res["k"] == 3 and res["silhouette"] > 0.7
    assert adjusted_rand_score(df["true"], res["data"]["cluster"]) > 0.95
    assert res["stability_mean_ari"] > 0.9 and res["ari_vs_hierarchical"] > 0.9
    assert res["profile"]["players"].sum() == len(df) and len(res["pca_explained"]) == 2


def test_choose_k_reports_silhouette_for_each_k() -> None:
    z = StandardScaler().fit_transform(planted_clusters()[["f0", "f1", "f2"]])
    sel = pm.choose_k(z)
    assert list(sel["k"]) == [2, 3, 4, 5, 6, 7]
    assert sel.loc[sel["silhouette"].idxmax(), "k"] in (2, 3)


def test_labels_are_unique_and_follow_the_profile() -> None:
    prof = pd.DataFrame(
        {
            "players": [50, 100, 90, 60],
            "mean_position": [8.5, 3.1, 4.0, 6.8],
            "rel_strike_rate": [0.76, 1.1, 0.87, 1.14],
            "rel_runs_per_innings": [0.34, 1.5, 0.92, 0.79],
            "boundary_share": [0.4, 0.56, 0.46, 0.55],
            "cv": [1.1, 0.9, 1.0, 1.0],
            "pct_30_plus": [0.03, 0.41, 0.22, 0.16],
            "not_out_pct": [0.34, 0.12, 0.09, 0.3],
        }
    )
    names = pm.label_clusters(prof, "batters")
    assert names == {
        0: "Lower-order contributors",
        1: "High-output top-order batters",
        3: "Finishers",
        2: "Middle-order accumulators",
    }
    # Labels follow the data: swap two rows and the names move with them.
    swapped = prof.iloc[[1, 0, 2, 3]].reset_index(drop=True)
    assert pm.label_clusters(swapped, "batters")[0] == "High-output top-order batters"


def test_regression_recovers_planted_effects() -> None:
    rng = np.random.default_rng(1)
    n = 4000
    groups = ["1-3", "4-5", "6-7", "8-11"]
    b = pd.DataFrame(
        {
            "player_id": rng.integers(0, 200, n),
            "position_group": pd.Categorical(rng.choice(groups, n), groups),
            "is_t20": rng.integers(0, 2, n),
            "knockout": rng.integers(0, 2, n),
            "chasing": rng.integers(0, 2, n),
            "elo_advantage": rng.normal(0, 1, n),
            "year_c": rng.normal(0, 5, n),
        }
    )
    b["log_runs"] = (
        2.5
        - 1.0 * (b["position_group"] == "8-11")
        + 0.3 * b["elo_advantage"]
        + rng.normal(0, 0.8, n)
    )
    b["high_score"] = (b["log_runs"] > 2.6).astype(int)
    fits = pm.fit_batting_models(b)
    t = pm.coefficient_table(fits["ols"]).set_index("term")
    assert t.loc["position 8-11", "estimate"] == pytest.approx(-1.0, abs=0.1)
    assert t.loc["elo_advantage", "estimate"] == pytest.approx(0.3, abs=0.05)
    assert abs(t.loc["knockout", "estimate"]) < 0.1 and t.loc["position 8-11", "p_value"] < 1e-6
    odds = pm.coefficient_table(fits["logit"], odds=True).set_index("term")
    assert odds.loc["position 8-11", "estimate"] < 1 < odds.loc["elo_advantage", "estimate"]


@pytest.mark.skipif(
    not (ROOT / "data/features/clusters_batters.parquet").exists(), reason="not built"
)
def test_real_clusters_respect_minimum_samples_and_have_labels() -> None:
    for kind, minimum in (("batters", pm.MIN_BAT_INNINGS), ("bowlers", pm.MIN_BOWL_INNINGS)):
        d = pd.read_parquet(ROOT / f"data/features/clusters_{kind}.parquet")
        assert d["innings"].min() >= minimum
        assert d["cluster_label"].notna().all() and d["cluster"].nunique() >= 3
        assert d["cluster"].value_counts().min() >= 8
