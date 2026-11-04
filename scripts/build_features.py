# ruff: noqa: E402
"""Stage 11: build the leakage-safe match feature table -> data/features/match_features.parquet."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.match_features import (
    build_match_features,
    load_matches,
    load_performances,
    write_catalog,
)  # noqa: E402


def main() -> int:
    feats = build_match_features(load_matches(), perf=load_performances())
    out = ROOT / "data" / "features" / "match_features.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(out, index=False)
    labelled = feats["y_a_wins"].notna().sum()
    print(f"{len(feats)} matches, {labelled} with a decided result -> {out.relative_to(ROOT)}")
    print(f"label balance (team A wins): {feats['y_a_wins'].mean():.3f}")
    print(f"catalog: {write_catalog(ROOT).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
