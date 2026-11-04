"""Stage 3: run the data-quality rules, score them and write reports (read-only on data)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.connection import get_engine  # noqa: E402
from src.validation.validate_data_quality import (  # noqa: E402
    collect_rules,
    persist_results,
    run_all,
    write_reports,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--layer",
        choices=["operational", "gold"],
        default="operational",
        help="operational = as-collected public tables (Stage 3); gold = resolved analytics schema",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="also replace this framework's rows in data_quality_results",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    engine = get_engine()
    if args.layer == "gold":
        from src.validation import validate_gold
        from src.validation.rules import validate_rule_ids

        rules = list(validate_gold.RULES)
        validate_rule_ids(rules)
        entity, out = "dq_rule_gold", args.out or ROOT / "reports" / "gold"
    else:
        rules = collect_rules(engine)
        entity, out = "dq_rule", args.out or ROOT / "reports"
    results, errors = run_all(engine, rules)
    persisted = persist_results(engine, results, entity) if args.persist else None
    paths = write_reports(results, errors, rules, out, persisted=persisted)

    failing = results[results["failed"] > 0]["rule_id"].nunique()
    print(
        f"Rules: {len(rules)} | evaluated: {results['rule_id'].nunique()} | failing: {failing} | could not run: {len(errors)}"
    )
    if len(errors):
        print(errors.to_string(index=False))
    print(f"Report: {paths['report']}")
    return 1 if len(errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
