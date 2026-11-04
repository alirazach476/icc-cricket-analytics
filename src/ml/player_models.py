# ruff: noqa: E501
"""Models 3-5: batting-performance regression, player clustering, player consistency.

All three describe *associations in historical data*; none makes causal claims. Minimum sample sizes are
explicit (batters >= 10 innings, bowlers >= 8 bowling innings) because per-player statistics on a handful of
innings are noise. Cluster labels are assigned *after* the profiles are computed, by a rule on the profile
itself, never before.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

SEED = 42
MIN_BAT_INNINGS = 10
MIN_BOWL_INNINGS = 8
MIN_BALLS_BOWLED_PER_INNINGS = 12
DB = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "cricket_gold.duckdb"


def load_performances(db: Path = DB) -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    try:
        perf = con.execute(
            "select f.*, p.full_name from gold.fact_player_performances f join gold.dim_players p using (player_id)"
        ).fetchdf()
    finally:
        con.close()
    return perf


# =========================================================================== Model 5: consistency
def batting_consistency(
    perf: pd.DataFrame, min_innings: int = MIN_BAT_INNINGS, n_boot: int = 300
) -> pd.DataFrame:
    b = perf[perf["did_bat"] & perf["runs"].notna()].copy()
    rng = np.random.default_rng(SEED)
    rows = []
    for pid, g in b.groupby("player_id"):
        if len(g) < min_innings:
            continue
        r = g["runs"].astype(float).to_numpy()
        boots = r[rng.integers(0, len(r), (n_boot, len(r)))].mean(axis=1)
        mean, sd = r.mean(), r.std(ddof=1)
        rows.append(
            {
                "player_id": pid,
                "player": g["full_name"].iloc[0],
                "innings": len(r),
                "mean_runs": mean,
                "median_runs": float(np.median(r)),
                "std_runs": sd,
                "cv": sd / mean if mean > 0 else np.nan,
                "pct_30_plus": float((r >= 30).mean()),
                "pct_ducks": float((r == 0).mean()),
                "mean_ci_low": float(np.percentile(boots, 2.5)),
                "mean_ci_high": float(np.percentile(boots, 97.5)),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_runs", ascending=False).reset_index(drop=True)


def bowling_consistency(
    perf: pd.DataFrame, min_innings: int = MIN_BOWL_INNINGS, n_boot: int = 300
) -> pd.DataFrame:
    b = perf[perf["did_bowl"] & (perf["balls_bowled"] >= MIN_BALLS_BOWLED_PER_INNINGS)].copy()
    b["econ"] = 6.0 * b["runs_conceded"] / b["balls_bowled"]
    rng = np.random.default_rng(SEED)
    rows = []
    for pid, g in b.groupby("player_id"):
        if len(g) < min_innings:
            continue
        e, w = g["econ"].to_numpy(), g["wickets"].astype(float).to_numpy()
        boots = e[rng.integers(0, len(e), (n_boot, len(e)))].mean(axis=1)
        rows.append(
            {
                "player_id": pid,
                "player": g["full_name"].iloc[0],
                "innings": len(e),
                "mean_economy": e.mean(),
                "median_economy": float(np.median(e)),
                "std_economy": e.std(ddof=1),
                "cv_economy": e.std(ddof=1) / e.mean(),
                "mean_wickets": w.mean(),
                "pct_wicketless": float((w == 0).mean()),
                "econ_ci_low": float(np.percentile(boots, 2.5)),
                "econ_ci_high": float(np.percentile(boots, 97.5)),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_economy").reset_index(drop=True)


# =========================================================================== Model 4: clustering
def batter_features(perf: pd.DataFrame, min_innings: int = MIN_BAT_INNINGS) -> pd.DataFrame:
    """Format-adjusted batting profile per player (SR and scoring are relative to each format's average)."""
    b = perf[perf["did_bat"] & perf["runs"].notna() & (perf["balls_faced"] > 0)].copy()
    fmt = b.groupby("format").agg(
        runs=("runs", "sum"), balls=("balls_faced", "sum"), inn=("runs", "size")
    )
    fmt["sr"], fmt["rpi"] = 100 * fmt["runs"] / fmt["balls"], fmt["runs"] / fmt["inn"]
    b["exp_runs_by_balls"] = b["balls_faced"] * b["format"].map(fmt["sr"]) / 100
    b["exp_runs_inn"] = b["format"].map(fmt["rpi"])
    rows = []
    for pid, g in b.groupby("player_id"):
        if len(g) < min_innings:
            continue
        r = g["runs"].astype(float)
        boundary_runs = 4 * g["fours"].fillna(0) + 6 * g["sixes"].fillna(0)
        rows.append(
            {
                "player_id": pid,
                "player": g["full_name"].iloc[0],
                "innings": len(g),
                "mean_position": g["batting_position"].mean(),
                "rel_strike_rate": r.sum() / g["exp_runs_by_balls"].sum(),
                "rel_runs_per_innings": r.sum() / g["exp_runs_inn"].sum(),
                "boundary_share": boundary_runs.sum() / max(r.sum(), 1.0),
                "cv": r.std(ddof=1) / r.mean() if r.mean() > 0 else np.nan,
                "pct_30_plus": float((r >= 30).mean()),
                "not_out_pct": float((~g["is_out"].fillna(True).astype(bool)).mean()),
            }
        )
    return pd.DataFrame(rows).dropna().reset_index(drop=True)


def bowler_features(perf: pd.DataFrame, min_innings: int = MIN_BOWL_INNINGS) -> pd.DataFrame:
    w = perf[perf["did_bowl"] & (perf["balls_bowled"] >= MIN_BALLS_BOWLED_PER_INNINGS)].copy()
    fe = w.groupby("format").agg(runs=("runs_conceded", "sum"), balls=("balls_bowled", "sum"))
    fe["econ"] = 6 * fe["runs"] / fe["balls"]
    w["exp_runs"] = w["balls_bowled"] * w["format"].map(fe["econ"]) / 6
    bat = (
        perf[perf["did_bat"] & perf["runs"].notna()]
        .groupby("player_id")
        .agg(bat_runs=("runs", "mean"), bat_pos=("batting_position", "mean"))
    )
    rows = []
    for pid, g in w.groupby("player_id"):
        if len(g) < min_innings:
            continue
        wk = g["wickets"].astype(float)
        balls = float(g["balls_bowled"].sum())
        rows.append(
            {
                "player_id": pid,
                "player": g["full_name"].iloc[0],
                "innings": len(g),
                "rel_economy": g["runs_conceded"].sum() / g["exp_runs"].sum(),
                "balls_per_wicket": balls / max(wk.sum(), 1.0),
                "wickets_per_innings": wk.mean(),
                "overs_per_innings": balls / 6 / len(g),
                "wicketless_pct": float((wk == 0).mean()),
                "bat_runs_per_innings": float(bat["bat_runs"].get(pid, 0.0)),
                "bat_position": float(bat["bat_pos"].get(pid, 11.0)),
            }
        )
    return pd.DataFrame(rows).dropna().reset_index(drop=True)


def choose_k(Z: np.ndarray, k_range=range(2, 8)) -> pd.DataFrame:
    rows = []
    for k in k_range:
        labels = KMeans(k, n_init=20, random_state=SEED).fit_predict(Z)
        rows.append(
            {
                "k": k,
                "silhouette": float(silhouette_score(Z, labels)),
                "smallest_cluster": int(np.bincount(labels).min()),
            }
        )
    return pd.DataFrame(rows)


def cluster_players(
    df: pd.DataFrame,
    feature_cols: list[str],
    k: int | None = None,
    n_boot: int = 100,
    min_k: int = 3,
    min_cluster: int = 8,
) -> dict:
    """KMeans + Ward hierarchical clustering, silhouette, bootstrap stability and a PCA projection.

    ``k`` defaults to the best silhouette among k >= ``min_k`` whose smallest cluster has >= ``min_cluster`` players
    (k=2 is excluded as a trivial split; tiny clusters are not interpretable profiles)."""
    scaler = StandardScaler()
    Z = scaler.fit_transform(df[feature_cols])
    sel = choose_k(Z)
    if k is None:
        ok = sel[(sel["k"] >= min_k) & (sel["smallest_cluster"] >= min_cluster)]
        k = int(
            (ok if len(ok) else sel[sel["k"] >= min_k])
            .sort_values("silhouette", ascending=False)["k"]
            .iloc[0]
        )
    km = KMeans(k, n_init=20, random_state=SEED).fit(Z)
    hier = fcluster(linkage(Z, "ward"), k, "maxclust") - 1
    rng = np.random.default_rng(SEED)
    aris = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(Z), len(Z))
        boot = KMeans(k, n_init=5, random_state=int(rng.integers(1_000_000))).fit(Z[idx])
        aris.append(adjusted_rand_score(km.labels_, boot.predict(Z)))
    pca = PCA(2, random_state=SEED).fit(Z)
    xy = pca.transform(Z)
    out = df.copy()
    out["cluster"] = km.labels_
    out["pc1"], out["pc2"] = xy[:, 0], xy[:, 1]
    profile = out.groupby("cluster")[feature_cols].mean()
    profile.insert(0, "players", out.groupby("cluster").size())
    z_profile = pd.DataFrame(km.cluster_centers_, columns=feature_cols)
    return {
        "data": out,
        "k": k,
        "selection": sel,
        "silhouette": float(silhouette_score(Z, km.labels_)),
        "ari_vs_hierarchical": float(adjusted_rand_score(km.labels_, hier)),
        "stability_mean_ari": float(np.mean(aris)),
        "stability_min_ari": float(np.min(aris)),
        "profile": profile,
        "z_profile": z_profile,
        "pca_explained": pca.explained_variance_ratio_.tolist(),
        "features": feature_cols,
    }


def describe_clusters(z_profile: pd.DataFrame, top: int = 3) -> dict[int, str]:
    """Plain-language description of each cluster from its standardised centroid (no pre-assigned names)."""
    out = {}
    for c, row in z_profile.iterrows():
        strong = row.reindex(row.abs().sort_values(ascending=False).index)[:top]
        out[int(c)] = ", ".join(
            f"{'high' if v > 0 else 'low'} {name.replace('_', ' ')} ({v:+.1f} sd)"
            for name, v in strong.items()
        )
    return out


def label_clusters(profile: pd.DataFrame, kind: str) -> dict[int, str]:
    """Names assigned AFTER inspecting the profiles, by rules on the profile itself (reproducible).

    If the rules do not give every cluster a distinct name (e.g. a different k), fall back to the plain
    description instead of forcing a label."""
    p = profile.drop(columns=["players"], errors="ignore")
    names: dict[int, str] = {}
    left = set(p.index)

    def take(label: str, series: pd.Series, largest: bool = True) -> None:
        c = int(series[list(left)].idxmax() if largest else series[list(left)].idxmin())
        names[c] = label
        left.discard(c)

    if kind == "batters":
        take("Lower-order contributors", p["mean_position"] - p["rel_runs_per_innings"])
        take(
            "High-output top-order batters",
            p["rel_runs_per_innings"] + p["pct_30_plus"] - p["mean_position"] / 5,
        )
        take("Finishers", p["rel_strike_rate"] + p["not_out_pct"] + p["mean_position"] / 5)
        for c in list(left):
            names[c] = "Middle-order accumulators"
    else:
        take("Strike bowlers", p["wickets_per_innings"])
        take(
            "Part-time bowlers / batting all-rounders",
            p["bat_runs_per_innings"] + p["wicketless_pct"],
        )
        take("Workhorse bowlers (long spells)", p["overs_per_innings"])
        for c in list(left):
            names[c] = "Short-spell attacking bowlers"
    return names if len(set(names.values())) == len(names) == len(p) else {}


# =========================================================================== Model 3: batting performance regression
def batting_innings_frame(perf: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Batting innings with pre-match context (opposition strength etc.) from the leakage-safe feature table."""
    b = perf[perf["did_bat"] & perf["runs"].notna() & perf["batting_position"].notna()].copy()
    elo = pd.concat(
        [
            features[["match_id", "team_a_id", "elo_a"]].rename(
                columns={"team_a_id": "team_id", "elo_a": "elo"}
            ),
            features[["match_id", "team_b_id", "elo_b"]].rename(
                columns={"team_b_id": "team_id", "elo_b": "elo"}
            ),
        ]
    )
    b = b.merge(elo, on=["match_id", "team_id"], how="left").merge(
        elo.rename(columns={"team_id": "opposition_team_id", "elo": "opp_elo"}),
        on=["match_id", "opposition_team_id"],
        how="left",
    )
    b["position_group"] = pd.cut(
        b["batting_position"], [0, 3, 5, 7, 12], labels=["1-3", "4-5", "6-7", "8-11"]
    )
    b["chasing"] = (b["batting_innings"] == 2).astype(int)
    b["elo_advantage"] = (b["elo"] - b["opp_elo"]) / 100
    b["high_score"] = (b["runs"] >= 30).astype(int)
    b["log_runs"] = np.log1p(b["runs"].astype(float))
    b["is_t20"] = (b["format"] == "T20").astype(int)
    b["knockout"] = b["is_knockout"].astype(int)
    b["year_c"] = b["year"] - b["year"].mean()
    return b.dropna(subset=["position_group", "elo_advantage", "batting_innings"])


FORMULA = (
    "C(position_group, Treatment('1-3')) + is_t20 + knockout + chasing + elo_advantage + year_c"
)


def fit_batting_models(b: pd.DataFrame) -> dict:
    """OLS on log(1+runs) and a logit for scoring 30+, with standard errors clustered by player."""
    groups = pd.factorize(b["player_id"])[0]
    ols = smf.ols(f"log_runs ~ {FORMULA}", b).fit(cov_type="cluster", cov_kwds={"groups": groups})
    logit = smf.logit(f"high_score ~ {FORMULA}", b).fit(
        disp=0, cov_type="cluster", cov_kwds={"groups": groups}
    )
    return {"ols": ols, "logit": logit, "n": len(b), "players": b["player_id"].nunique()}


def coefficient_table(fit, odds: bool = False) -> pd.DataFrame:
    ci = fit.conf_int()
    t = pd.DataFrame(
        {
            "term": fit.params.index,
            "estimate": fit.params.values,
            "ci_low": ci[0].values,
            "ci_high": ci[1].values,
            "p_value": fit.pvalues.values,
        }
    )
    t["term"] = (
        t["term"]
        .str.replace(r"C\(position_group, Treatment\('1-3'\)\)\[T\.", "position ", regex=True)
        .str.replace("]", "", regex=False)
    )
    if odds:
        for c in ("estimate", "ci_low", "ci_high"):
            t[c] = np.exp(t[c])
    return t[t["term"] != "Intercept"].reset_index(drop=True)
