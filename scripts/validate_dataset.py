"""Validate normalized World Cup dataset (Stage 9)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import get_logger
from src.validation.validate_dataset import validate_dataset

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate normalized cricket World Cup data.")
    parser.add_argument("--tournament", help="Limit to one tournament_id, e.g. ODI_M_2023")
    parser.add_argument(
        "--match",
        action="append",
        dest="matches",
        help="Limit to match_id values (repeatable).",
    )
    parser.add_argument("--limit", type=int, help="Validate at most N matches.")
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Skip tournament coverage snapshot / gaps.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_dataset(
        tournament_id=args.tournament,
        match_ids=args.matches,
        limit=args.limit,
        include_coverage=not args.no_coverage,
    )
    if args.json:
        # Omit per-match issue details unless small
        slim = {k: v for k, v in report.items() if k != "match_results"}
        slim["match_results"] = [
            {
                "match_id": r.get("match_id"),
                "ok": r.get("ok"),
                "issue_summary": r.get("issue_summary"),
            }
            for r in report.get("match_results") or []
        ]
        print(json.dumps(slim, indent=2, default=str))
    else:
        summary = report.get("issue_summary") or {}
        print("Validation finished.")
        print(f"  tournament={report.get('tournament_id')}")
        print(f"  matches_validated={report.get('matches_validated')}")
        print(f"  matches_ok={report.get('matches_ok')}")
        print(f"  matches_failed={report.get('matches_failed')}")
        for key, value in summary.items():
            print(f"  issues_{key}={value}")
        cov = report.get("coverage") or {}
        if cov:
            print(
                f"  coverage: discovered={cov.get('discovered_matches')} "
                f"scorecards={cov.get('scorecards_collected')} "
                f"normalized={cov.get('normalized_matches')} "
                f"bbb_complete={((cov.get('ball_by_ball') or {}).get('complete'))}"
            )
            print(f"  claims_complete_coverage={cov.get('claims_complete_coverage')}")
        print(f"  report={report.get('report_path')}")
        print(f"  issues_csv={report.get('issues_csv_path')}")

    # Non-zero exit if any errors (warnings/info still 0)
    return 1 if (report.get("issue_summary") or {}).get("error", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
