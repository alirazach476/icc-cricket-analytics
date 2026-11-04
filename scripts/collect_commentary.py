"""Collect ball-by-ball / commentary data (Stage 7).

Sources:
  --source espn       ESPNcricinfo commentary HTML (typically partial)
  --source cricsheet  Cricsheet WC JSON bundles (complete when identity-verified)
  --source both       Prefer Cricsheet for complete BBB; ESPN for partial commentary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.commentary_collector import collect_commentary
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect World Cup ball-by-ball / commentary.")
    parser.add_argument("--tournament", help="Limit to one tournament_id, e.g. ODI_M_2023")
    parser.add_argument(
        "--match",
        action="append",
        dest="matches",
        help="Limit to match_id values (repeatable).",
    )
    parser.add_argument("--limit", type=int, help="Collect at most N matches from the filtered set.")
    parser.add_argument(
        "--source",
        choices=("espn", "cricsheet", "both"),
        default="both",
        help="BBB source strategy (default: both).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-collect ESPN even if commentary_espn.json exists.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = collect_commentary(
        tournament_id=args.tournament,
        match_ids=args.matches,
        limit=args.limit,
        source=args.source,
        use_cache=not args.no_cache,
        force=args.force,
        live=not args.dry_run,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        summary = report.get("summary") or {}
        print("Commentary / BBB collection finished.")
        print(f"  source={report.get('source')}")
        print(f"  targeted={report.get('targeted')}")
        for key, value in summary.items():
            print(f"  {key}={value}")
        if report.get("espn_stopped"):
            print(f"  ESPN STOPPED: {report.get('stop_reason')}")
        print(f"  report={report.get('report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
