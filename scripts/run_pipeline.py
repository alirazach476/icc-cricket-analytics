"""Incremental ETL pipeline (Stages 10–11).

Default: normalize → validate → load → warehouse for already-collected data.
Pass --collect to also run scorecard + commentary collection first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.orchestrator import STAGE_ORDER, run_pipeline
from src.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CricketWorldCup Analytics pipeline stages.")
    parser.add_argument("--tournament", help="Limit to one tournament_id, e.g. ODI_M_2023")
    parser.add_argument("--match", action="append", dest="matches", help="Limit to match_id(s).")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--stages",
        help=f"Comma-separated stages. Default: normalize,validate,load. Options: {','.join(STAGE_ORDER)}",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Include collect_scorecards + collect_commentary before normalize.",
    )
    parser.add_argument(
        "--source",
        choices=("espn", "cricsheet", "both"),
        default="cricsheet",
        help="Commentary source when collecting.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stages:
        stages = [s.strip() for s in args.stages.split(",") if s.strip()]
        skip_collect = False
    elif args.collect:
        stages = list(STAGE_ORDER)
        skip_collect = False
    else:
        stages = ["normalize", "validate", "load", "warehouse"]
        skip_collect = True

    report = run_pipeline(
        tournament_id=args.tournament,
        match_ids=args.matches,
        limit=args.limit,
        stages=stages,
        dry_run=args.dry_run,
        force=args.force,
        source=args.source,
        skip_collect=skip_collect,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Pipeline finished.")
        print(f"  tournament={report.get('tournament_id')}")
        print(f"  stages={report.get('stages')}")
        print(f"  dry_run={report.get('dry_run')}")
        for name, stage_report in (report.get("stage_reports") or {}).items():
            summary = stage_report.get("summary") if isinstance(stage_report, dict) else None
            if summary:
                print(f"  {name}: {summary}")
            elif isinstance(stage_report, dict) and "matches_ok" in stage_report:
                print(
                    f"  {name}: ok={stage_report.get('matches_ok')} "
                    f"failed={stage_report.get('matches_failed')} "
                    f"errors={(stage_report.get('issue_summary') or {}).get('error')}"
                )
            elif isinstance(stage_report, dict) and "total_rows" in stage_report:
                print(
                    f"  {name}: total_rows={stage_report.get('total_rows')} "
                    f"duckdb={stage_report.get('duckdb_path')}"
                )
            else:
                print(f"  {name}: done")
        print(f"  report={report.get('report_path')}")

    # Fail if validate found errors or load failed any matches
    stages = report.get("stage_reports") or {}
    validate = stages.get("validate") or {}
    load = stages.get("load") or {}
    if (validate.get("issue_summary") or {}).get("error"):
        return 1
    if (load.get("summary") or {}).get("failed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
