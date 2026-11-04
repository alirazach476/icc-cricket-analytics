"""Validate registry and run Stage 4 tournament discovery against ESPNcricinfo.

Live HTTP is attempted only when --live is set (default). If the source returns
401/403/429, discovery stops gracefully and records access_restricted outcomes.
No fabricated tournament/match records are created.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.discovery.tournament_discovery import discover_tournaments
from src.discovery.tournament_registry import load_tournament_registry
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover / verify World Cup tournament pages.")
    parser.add_argument(
        "--tournament",
        action="append",
        dest="tournaments",
        help="Limit to one or more tournament_id values (repeatable).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate registry only; do not perform HTTP collection.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not reuse previously saved raw HTML.",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Write discovery status into PostgreSQL when available.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_tournament_registry()
    report = discover_tournaments(
        registry=registry,
        tournament_ids=args.tournaments,
        live=not args.dry_run,
        use_cache=not args.no_cache,
        update_database=args.update_db,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        summary = report["summary"]
        print("Tournament discovery finished.")
        print(f"  targeted={report['total_targeted']}")
        for key, value in summary.items():
            if value:
                print(f"  {key}={value}")
        if report.get("collector_stopped"):
            print(f"  STOPPED: {report.get('stop_reason')}")
        print(f"  report={report.get('report_path')}")
        if summary.get("access_restricted"):
            print(
                "  NOTE: ESPNcricinfo blocked automated HTTP (access restricted). "
                "Raw pages were not collected. Parsers/fixtures remain available for offline work."
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
