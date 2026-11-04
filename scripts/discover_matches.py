"""Discover match URLs for one or more World Cup tournaments (Stage 5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.discovery.match_discovery import discover_matches
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover World Cup match URLs from ESPNcricinfo.")
    parser.add_argument(
        "--tournament",
        action="append",
        dest="tournaments",
        help="Tournament id (repeatable). Example: --tournament ODI_M_2023",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not perform HTTP/cache parsing.")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached schedule HTML.")
    parser.add_argument("--update-db", action="store_true", help="Update PostgreSQL match counts when available.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = discover_matches(
        tournament_ids=args.tournaments,
        live=not args.dry_run,
        use_cache=not args.no_cache,
        update_database=args.update_db,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        summary = report["summary"]
        print("Match discovery finished.")
        print(f"  tournaments={report['total_tournaments']}")
        print(f"  matches={report['total_matches_discovered']}")
        print(f"  scorecard_urls={summary.get('matches_with_scorecard_url')}")
        print(f"  commentary_urls={summary.get('matches_with_commentary_url')}")
        print(f"  access={summary.get('tournaments_by_access')}")
        if report.get("collector_stopped"):
            print(f"  STOPPED: {report.get('stop_reason')}")
        print(f"  manifest={report.get('manifest_path')}")
        print(f"  report={report.get('report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
