"""After bulk collection: normalize → validate → load → warehouse → dbt for all data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.load_processed import load_processed
from src.transformations.normalize_collected import normalize_collected
from src.utils.logger import get_logger
from src.validation.validate_dataset import validate_dataset
from src.warehouse.duckdb_warehouse import sync_warehouse

logger = get_logger(__name__)


def main() -> int:
    print("1/5 normalize_collected (all with scorecards)...")
    norm = normalize_collected(force=False)
    print("   ", norm.get("summary"))

    print("2/5 validate_dataset...")
    val = validate_dataset(include_coverage=True)
    print(
        "   ",
        f"ok={val.get('matches_ok')} failed={val.get('matches_failed')} "
        f"errors={(val.get('issue_summary') or {}).get('error')}",
    )

    print("3/5 load_processed -> Postgres...")
    load = load_processed(dry_run=False)
    print("   ", load.get("summary"))

    print("4/5 sync_warehouse -> DuckDB/Parquet...")
    wh = sync_warehouse(replace_duckdb=True)
    print("   ", f"total_rows={wh.get('total_rows')} duckdb={wh.get('duckdb_path')}")

    print("5/5 dbt build...")
    dbt = PROJECT_ROOT / ".venv" / "Scripts" / "dbt.exe"
    cmd = [
        str(dbt),
        "build",
        "--project-dir",
        str(PROJECT_ROOT / "dbt"),
        "--profiles-dir",
        str(PROJECT_ROOT / "dbt"),
        "--target",
        "dev",
    ]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    print("    dbt returncode=", completed.returncode)

    report = {
        "normalize": norm.get("summary"),
        "validate": {
            "matches_ok": val.get("matches_ok"),
            "matches_failed": val.get("matches_failed"),
            "issue_summary": val.get("issue_summary"),
            "coverage": val.get("coverage"),
        },
        "load": load.get("summary"),
        "warehouse_total_rows": wh.get("total_rows"),
        "dbt_returncode": completed.returncode,
    }
    out = PROJECT_ROOT / "data" / "processed" / "validation" / "bulk_pipeline_all_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("report=", out)
    return 0 if completed.returncode == 0 and not (load.get("summary") or {}).get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
