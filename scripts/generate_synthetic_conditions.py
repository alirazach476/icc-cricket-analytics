# ruff: noqa: E501
"""Generate SYNTHETIC pitch/weather/day-night placeholders -> data/synthetic (not real data).

python scripts/generate_synthetic_conditions.py [--seed N]
python scripts/load_warehouse.py        # then loads analytics.synthetic_match_conditions
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.synthetic.match_conditions import DEFAULT_SEED, build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    out = build(ROOT, args.seed)
    print(
        f"SYNTHETIC data written: {out.relative_to(ROOT)} (seed {args.seed}). Not real observations."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
