"""Build the Champions Trophy and World Test Championship data (Cricsheet -> silver -> gold -> DuckDB)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.competitions.pipeline import run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", action="append", choices=["CT", "WTC", "WC27"])
    ap.add_argument(
        "--wc2027", action="store_true", help="only rebuild the upcoming 2027 World Cup data"
    )
    ap.add_argument("--refresh", action="store_true", help="download the Cricsheet archives again")
    a = ap.parse_args()
    codes = ("WC27",) if a.wc2027 else tuple(a.code or ("CT", "WTC", "WC27"))
    s = run(codes, force_download=a.refresh)
    for code, c in s["competitions"].items():
        print(
            code,
            c["matches_per_year"],
            "gaps:",
            [(g["year"], g["have"], g["scheduled"]) for g in c["coverage_gaps"]],
        )
    print(json.dumps({"report": "reports/competitions_report.md"}))


if __name__ == "__main__":
    main()
