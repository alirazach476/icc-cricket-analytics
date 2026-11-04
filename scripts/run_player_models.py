# ruff: noqa: E501
"""Models 3-5: consistency, clustering and batting-performance regression -> reports + data/features."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import player_models as pm  # noqa: E402

BAT_FEATURES = [
    "mean_position",
    "rel_strike_rate",
    "rel_runs_per_innings",
    "boundary_share",
    "cv",
    "pct_30_plus",
    "not_out_pct",
]
BOWL_FEATURES = [
    "rel_economy",
    "balls_per_wicket",
    "wickets_per_innings",
    "overs_per_innings",
    "wicketless_pct",
    "bat_runs_per_innings",
]


def main() -> int:
    perf = pm.load_performances()
    out = ROOT / "reports" / "model_evaluation"
    out.mkdir(parents=True, exist_ok=True)
    feat_dir = ROOT / "data" / "features"

    bc, wc = pm.batting_consistency(perf), pm.bowling_consistency(perf)
    bc.to_csv(out / "consistency_batting.csv", index=False)
    wc.to_csv(out / "consistency_bowling.csv", index=False)

    results = {}
    for name, df, cols in (
        ("batters", pm.batter_features(perf), BAT_FEATURES),
        ("bowlers", pm.bowler_features(perf), BOWL_FEATURES),
    ):
        res = pm.cluster_players(df, cols)
        results[name] = res
        labels = pm.label_clusters(res["profile"], name)
        res["labels"] = labels or pm.describe_clusters(res["z_profile"])
        res["data"]["cluster_label"] = res["data"]["cluster"].map(res["labels"])
        pd.Series(res["labels"], name="label").rename_axis("cluster").to_csv(
            out / f"clusters_{name}_labels.csv"
        )
        res["data"].to_parquet(feat_dir / f"clusters_{name}.parquet", index=False)
        res["selection"].to_csv(out / f"clusters_{name}_k_selection.csv", index=False)
        res["profile"].to_csv(out / f"clusters_{name}_profile.csv")
        res["z_profile"].to_csv(out / f"clusters_{name}_zprofile.csv")
        print(
            f"\n=== {name}: n={len(df)} k={res['k']} silhouette={res['silhouette']:.3f} ARI(hier)={res['ari_vs_hierarchical']:.2f} stability={res['stability_mean_ari']:.2f} (min {res['stability_min_ari']:.2f}) PCA var={[round(v, 2) for v in res['pca_explained']]}"
        )
        print(res["selection"].round(3).to_string(index=False))
        print(res["profile"].round(2).to_string())
        print("  labels:", res["labels"])
        for c, d in pm.describe_clusters(res["z_profile"]).items():
            ex = (
                res["data"][res["data"].cluster == c]
                .sort_values("innings", ascending=False)["player"]
                .head(5)
                .tolist()
            )
            print(f"  cluster {c}: {d}\n     e.g. {ex}")

    b = pm.batting_innings_frame(perf, pd.read_parquet(feat_dir / "match_features.parquet"))
    fits = pm.fit_batting_models(b)
    pm.coefficient_table(fits["ols"]).to_csv(out / "batting_regression_ols.csv", index=False)
    pm.coefficient_table(fits["logit"], odds=True).to_csv(
        out / "batting_regression_logit_odds.csv", index=False
    )
    print(
        f"\n=== batting regression: n={fits['n']} innings, {fits['players']} players; OLS R2={fits['ols'].rsquared:.3f}; logit pseudo-R2={fits['logit'].prsquared:.3f}"
    )
    print(pm.coefficient_table(fits["ols"]).round(3).to_string(index=False))
    print(pm.coefficient_table(fits["logit"], odds=True).round(3).to_string(index=False))
    print(f"\nconsistency: {len(bc)} batters, {len(wc)} bowlers with min samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
