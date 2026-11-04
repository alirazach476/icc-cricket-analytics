"""Load normalized processed JSON into PostgreSQL (Stage 10)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.load_processed import load_processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed match bundles into PostgreSQL.")
    parser.add_argument("--tournament", help="Limit to one tournament_id")
    parser.add_argument("--match", action="append", dest="matches")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_processed(
        tournament_id=args.tournament,
        match_ids=args.matches,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        summary = report.get("summary") or {}
        print("DB load finished.")
        print(f"  tournament={report.get('tournament_id')}")
        for key, value in summary.items():
            print(f"  {key}={value}")
        print(f"  collection_run_id={report.get('collection_run_id')}")
        print(f"  report={report.get('report_path')}")
    return 1 if (report.get("summary") or {}).get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
