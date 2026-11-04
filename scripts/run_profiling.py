"""Stage 2: read-only data profiling and audit. Writes reports/ only."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.connection import get_engine  # noqa: E402
from src.profiling.generate_data_audit import run_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "reports", help="output directory (default: reports/)"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("src.database").setLevel(logging.WARNING)
    ctx = run_audit(ROOT, get_engine(), args.out)
    sev = {}
    for f in ctx["findings"]:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    print(f"\nDatasets profiled/inventoried: {len(ctx['inventory'])}")
    print(f"Findings: {sev}")
    print(f"Reports written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
