"""Normalize collected raw scorecards / BBB into data/processed (Stage 8)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.transformations.normalize_collected import normalize_collected
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize collected World Cup match data.")
    parser.add_argument("--tournament", help="Limit to one tournament_id, e.g. ODI_M_2023")
    parser.add_argument(
        "--match",
        action="append",
        dest="matches",
        help="Limit to match_id values (repeatable).",
    )
    parser.add_argument("--limit", type=int, help="Process at most N matches from the filtered set.")
    parser.add_argument("--force", action="store_true", help="Re-write even if processed file exists.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = normalize_collected(
        tournament_id=args.tournament,
        match_ids=args.matches,
        limit=args.limit,
        force=args.force,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        summary = report.get("summary") or {}
        print("Normalization finished.")
        print(f"  tournament={report.get('tournament_id')}")
        for key, value in summary.items():
            print(f"  {key}={value}")
        print(f"  teams={report.get('teams_path')}")
        print(f"  report={report.get('report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
