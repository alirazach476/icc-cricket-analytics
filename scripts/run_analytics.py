"""Run Stage 13 analytics reports against dbt marts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics.run_analytics import run_tournament_analytics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute tournament analytics from DuckDB marts.")
    parser.add_argument(
        "--tournament",
        required=True,
        help="Tournament id, e.g. ODI_M_2023",
    )
    parser.add_argument("--limit", type=int, default=15, help="Leaderboard size (default 15).")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_tournament_analytics(tournament_id=args.tournament, limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"Analytics failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    sections = report.get("sections") or {}
    batting = (sections.get("batting_leaders") or {}).get("leaders") or []
    bowling = (sections.get("bowling_leaders") or {}).get("leaders") or []
    coverage = (sections.get("tournament") or {}).get("coverage") or {}
    teams = (sections.get("teams") or {}).get("match_records") or []

    print("Analytics finished.")
    print(f"  tournament={report.get('tournament_id')}")
    print(f"  claims_complete_coverage={report.get('claims_complete_coverage')}")
    if coverage:
        print(
            f"  coverage: matches={coverage.get('matches_loaded')} "
            f"bbb_complete={coverage.get('matches_bbb_complete')} "
            f"deliveries={coverage.get('delivery_rows')}"
        )
    print("  top batting:")
    for row in batting[:5]:
        print(f"    {row.get('player_name')}: {row.get('runs')} runs ({row.get('innings_batted')} inns)")
    print("  top bowling:")
    for row in bowling[:5]:
        print(f"    {row.get('player_name')}: {row.get('wickets')} wickets")
    print("  team wins:")
    for row in teams[:5]:
        print(f"    {row.get('team_name')}: {row.get('wins')}/{row.get('matches_played')}")
    print(f"  report={report.get('report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
