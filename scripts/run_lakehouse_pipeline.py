# ruff: noqa: E501
"""Stage 15: run the end-to-end analytics pipeline.

python scripts/run_lakehouse_pipeline.py                  # everything (synthetic step excluded)
python scripts/run_lakehouse_pipeline.py --dry-run        # show the plan only
python scripts/run_lakehouse_pipeline.py --from warehouse --to quality_gold
python scripts/run_lakehouse_pipeline.py --only stats,train
python scripts/run_lakehouse_pipeline.py --with synthetic # also generate SYNTHETIC placeholders
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline.lakehouse_pipeline import ORDER, STEPS, run_pipeline, select_steps  # noqa: E402


def csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--from", dest="start", choices=ORDER)
    p.add_argument("--to", dest="stop", choices=ORDER)
    p.add_argument("--only", type=csv)
    p.add_argument("--skip", type=csv)
    p.add_argument(
        "--with", dest="with_optional", type=csv, help="optional steps to include, e.g. synthetic"
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    if a.list:
        for s in STEPS:
            print(f"{s.name:14} {'(optional) ' if s.optional else ''}{s.description}")
        return 0
    steps = select_steps(a.only, a.start, a.stop, a.skip, a.with_optional)
    results = run_pipeline(steps, dry_run=a.dry_run)
    width = max(len(r.name) for r in results)
    for r in results:
        print(f"{r.name:{width}}  {r.status:11} {r.seconds:7.1f}s  {r.message}")
    failed = [r for r in results if r.status not in ("ok", "dry_run")]
    skipped = [r.name for r in results if r.status == "skipped"]
    print(
        "\nPIPELINE "
        + (
            "OK"
            if not failed
            else f"FAILED at {failed[0].name}"
            + (f"; not run: {', '.join(skipped)}" if skipped else "")
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
