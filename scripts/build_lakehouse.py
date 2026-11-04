"""Stage 4: build the bronze / silver / gold layers from the collected data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.bronze import build_bronze, verify_bronze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", choices=["bronze", "silver", "gold", "all"], default="all")
    parser.add_argument("--verify", action="store_true", help="re-hash bronze against its manifest")
    args = parser.parse_args()

    if args.verify:
        problems = verify_bronze(ROOT)
        print("bronze intact" if not problems else "\n".join(problems))
        return 1 if problems else 0

    if args.layer in {"bronze", "all"}:
        for r in build_bronze(ROOT):
            print(
                f"bronze  {r['entity']:22} {r['status']:9} rows={r['rows']:>8}  batch={r['batch_id']}"
            )
    if args.layer in {"silver", "all"}:
        from src.transformations.silver import build_silver

        print(json.dumps(build_silver(ROOT), indent=2, default=str))
    if args.layer in {"gold", "all"}:
        from src.transformations.gold import build_gold

        print(json.dumps(build_gold(ROOT), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
