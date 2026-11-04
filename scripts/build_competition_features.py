# ruff: noqa: E402, E501
"""Leakage-safe match features and Elo ratings for the Champions Trophy and the World Test Championship.

Reuses the World Cup feature builder unchanged (``src.features.match_features``): every feature of a match uses only
matches on strictly earlier dates. Writes ``data/features/<code>_match_features.parquet`` and
``reports/model_evaluation/<code>_elo_ratings.csv`` (the rating of every team after the last match).

    python scripts/build_competition_features.py            # ct and wtc
    python scripts/build_competition_features.py --code wtc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd
from src.features.match_features import (
    ELO_K,
    ELO_START,
    build_match_features,
    load_matches,
    load_performances,
)

DBS = {
    "ct": ROOT / "data" / "warehouse" / "cricket_gold_ct.duckdb",
    "wtc": ROOT / "data" / "warehouse" / "cricket_gold_wtc.duckdb",
}


def run(code: str) -> None:
    db = DBS[code]
    matches = load_matches(db)
    feats, elo = build_match_features(matches, return_state=True, perf=load_performances(db))
    out = ROOT / "data" / "features" / f"{code}_match_features.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(out, index=False)

    con = duckdb.connect(str(db), read_only=True)
    names = dict(con.execute("select team_id, team_name from gold.dim_teams").fetchall())
    con.close()
    ratings = (
        pd.DataFrame([(fmt, names.get(t, t), r) for (fmt, t), r in elo.items()], columns=["format", "team", "elo"])
        .sort_values("elo", ascending=False)
        .reset_index(drop=True)
    )
    ratings["elo"] = ratings["elo"].round(1)
    rpath = ROOT / "reports" / "model_evaluation" / f"{code}_elo_ratings.csv"
    ratings.to_csv(rpath, index=False)

    labelled = int(feats["y_a_wins"].notna().sum())
    print(f"\n[{code}] {len(feats)} matches, {labelled} with a decided result (no label for draws, ties, abandoned)")
    print(f"       Elo: start {ELO_START:.0f}, K {ELO_K:.0f}, updated after decided matches; a Test draw counts as half a win")
    print(f"       sum of ratings = {ratings['elo'].sum():.1f} (should be {ELO_START * len(ratings):.1f}: Elo only moves points)")
    print(f"       features -> {out.relative_to(ROOT)}   ratings -> {rpath.relative_to(ROOT)}")
    print(ratings.head(8).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", choices=sorted(DBS))
    args = ap.parse_args()
    for c in [args.code] if args.code else sorted(DBS):
        run(c)
