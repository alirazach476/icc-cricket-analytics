"""Collect standings and squads for all (or one) tournament edition(s)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.standings_collector import collect_standings_and_squads  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", help="e.g. T20_M_2007 (default: all)")
    parser.add_argument("--only", choices=["standings", "squads"], help="Collect just one")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if cached")
    args = parser.parse_args()

    what = (args.only,) if args.only else ("standings", "squads")
    report = collect_standings_and_squads(
        tournament_id=args.tournament, what=what, force=args.force
    )
    print(json.dumps(report, indent=2, default=str))
    return 1 if report["stopped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
