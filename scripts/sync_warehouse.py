"""Sync PostgreSQL → DuckDB + Parquet (Stage 11)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.warehouse.duckdb_warehouse import WAREHOUSE_TABLES, sync_warehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync cricket warehouse to DuckDB and Parquet.")
    parser.add_argument("--tournament", help="Limit export to one tournament_id (separate DuckDB file).")
    parser.add_argument(
        "--tables",
        help=f"Comma-separated tables. Default: all. Options: {','.join(WAREHOUSE_TABLES)}",
    )
    parser.add_argument("--no-parquet", action="store_true", help="Skip writing Parquet files.")
    parser.add_argument(
        "--replace-duckdb",
        action="store_true",
        help="Delete the target DuckDB file before sync.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tables = [t.strip() for t in args.tables.split(",")] if args.tables else None
    report = sync_warehouse(
        tournament_id=args.tournament,
        tables=tables,
        write_parquet=not args.no_parquet,
        replace_duckdb=args.replace_duckdb,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Warehouse sync finished.")
        print(f"  tournament={report.get('tournament_id')}")
        print(f"  duckdb={report.get('duckdb_path')}")
        print(f"  parquet_dir={report.get('parquet_dir')}")
        print(f"  total_rows={report.get('total_rows')}")
        for name, stats in (report.get("tables") or {}).items():
            print(f"  {name}: rows={stats.get('rows')}")
        print(f"  claims_complete_coverage={report.get('claims_complete_coverage')}")
        print(f"  manifest={report.get('manifest_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
