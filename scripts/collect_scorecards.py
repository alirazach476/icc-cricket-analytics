"""Collect ESPNcricinfo full scorecards for discovered matches (Stage 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.scorecard_collector import collect_scorecards
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect World Cup match scorecards.")
    parser.add_argument("--tournament", help="Limit to one tournament_id, e.g. ODI_M_2023")
    parser.add_argument(
        "--match",
        action="append",
        dest="matches",
        help="Limit to match_id values (repeatable).",
    )
    parser.add_argument("--limit", type=int, help="Collect at most N matches from the filtered set.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-collect even if scorecard.json exists.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = collect_scorecards(
        tournament_id=args.tournament,
        match_ids=args.matches,
        limit=args.limit,
        use_cache=not args.no_cache,
        force=args.force,
        live=not args.dry_run,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        summary = report.get("summary") or {}
        print("Scorecard collection finished.")
        print(f"  targeted={report.get('targeted')}")
        for key, value in summary.items():
            print(f"  {key}={value}")
        if report.get("collector_stopped"):
            print(f"  STOPPED: {report.get('stop_reason')}")
        print(f"  report={report.get('report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
