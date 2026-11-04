"""Stage 6: load the gold layer into PostgreSQL (analytics schema) and DuckDB.

python scripts/load_warehouse.py                # postgres + duckdb + DDL file
python scripts/load_warehouse.py --target duckdb
python scripts/load_warehouse.py --reset        # drop + recreate the analytics schema first
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.connection import get_engine  # noqa: E402
from src.warehouse.load_gold import (  # noqa: E402
    drop_schema,
    load_duckdb,
    load_postgres,
    postgres_counts,
    write_ddl,
    write_design_doc,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["postgres", "duckdb", "all"], default="all")
    parser.add_argument("--reset", action="store_true", help="drop the analytics schema first")
    args = parser.parse_args()

    print(f"DDL: {write_ddl(ROOT)}")
    if args.target in ("postgres", "all"):
        engine = get_engine()
        if args.reset:
            drop_schema(engine)
            print("analytics schema dropped")
        results = load_postgres(engine, ROOT)
        print(f"{'table':32}{'source':>9}{'inserted':>10}{'updated':>9}{'deleted':>9}")
        for r in results:
            print(
                f"{r['table']:32}{r['source_rows']:>9}{r['inserted']:>10}{r['updated']:>9}{r['deleted']:>9}"
            )
        db = postgres_counts(engine)
        print(f"Design doc: {write_design_doc(ROOT, db)}")
        bad = [r["table"] for r in results if db[r["table"]] != r["source_rows"]]
        print("postgres row counts match gold" if not bad else f"MISMATCH: {bad}")
        if bad:
            return 1
    if args.target in ("duckdb", "all"):
        counts = load_duckdb(ROOT)
        print(f"duckdb: {len(counts)} tables, {sum(counts.values()):,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
