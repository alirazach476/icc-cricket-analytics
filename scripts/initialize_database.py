"""Initialize project directories, PostgreSQL schema, and seed reference data.

Usage:
  python scripts/initialize_database.py
  python scripts/initialize_database.py --skip-db
  python scripts/initialize_database.py --reset-schema
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import check_connection, get_engine, reset_engine_cache, session_scope
from src.database.schema import create_schema, drop_schema, list_tables
from src.database.seed_data import seed_reference_data
from src.discovery.tournament_registry import (
    load_tournament_registry,
    sync_tournament_manifest,
)
from src.utils.config import get_project_root, get_settings
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

REQUIRED_DIRS = [
    "data/raw/tournaments",
    "data/raw/matches",
    "data/raw/scorecards",
    "data/raw/commentary",
    "data/processed/tournaments",
    "data/processed/matches",
    "data/processed/innings",
    "data/processed/deliveries",
    "data/processed/players",
    "data/processed/standings",
    "data/processed/analytics",
    "data/warehouse/parquet",
    "data/manifests",
    "logs",
    "config",
]

REQUIRED_TABLES = {
    "tournaments",
    "teams",
    "players",
    "matches",
    "match_teams",
    "innings",
    "deliveries",
    "batting_scorecards",
    "bowling_scorecards",
    "fielding_scorecards",
    "standings",
    "tournament_awards",
    "match_events",
    "sources",
    "collection_runs",
    "data_quality_results",
}


def ensure_directories(root: Path) -> None:
    for relative in REQUIRED_DIRS:
        ensure_dir(root / relative)
        logger.info("Directory ready: %s", relative)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize CricketWorldCup Analytics database.")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Only sync local directories/manifest; skip PostgreSQL.",
    )
    parser.add_argument(
        "--reset-schema",
        action="store_true",
        help="Drop and recreate all ORM tables before seeding (destructive).",
    )
    return parser.parse_args()


def initialize_postgres(*, reset_schema: bool = False) -> dict:
    reset_engine_cache()
    engine = get_engine()
    check_connection()
    logger.info("PostgreSQL connection OK")

    if reset_schema:
        logger.warning("Resetting schema (drop + create)")
        drop_schema(engine)

    create_schema(engine)
    tables = set(list_tables(engine))
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise RuntimeError(f"Missing required tables after create_schema: {missing}")

    with session_scope() as session:
        seed_result = seed_reference_data(session)

    seed_result["tables"] = sorted(tables)
    seed_result["required_table_count"] = len(REQUIRED_TABLES)
    return seed_result


def main() -> int:
    args = parse_args()
    root = get_project_root()
    settings = get_settings()
    logger.info("Initializing project at %s", root)
    logger.info("App: %s v%s", settings["app"]["name"], settings["app"]["version"])
    logger.info("Bootstrap timestamp (UTC): %s", utc_now_iso())

    ensure_directories(root)
    registry = load_tournament_registry()
    sync_tournament_manifest(registry, root=root)
    print(f"OK - Manifest synced ({len(registry.tournaments)} tournaments).")

    if args.skip_db:
        print("Skipped PostgreSQL (--skip-db).")
        return 0

    try:
        result = initialize_postgres(reset_schema=args.reset_schema)
    except Exception as exc:  # noqa: BLE001 - surface clear CLI guidance
        logger.error("PostgreSQL initialization failed: %s", exc)
        print(
            "ERROR - PostgreSQL init failed. "
            "Start Docker Postgres with: docker compose up -d postgres\n"
            f"Details: {exc}"
        )
        return 1

    print(
        "OK - PostgreSQL ready: "
        f"{result['required_table_count']} required tables present, "
        f"{result['tournament_count']} tournaments seeded, "
        f"sources={list(result['sources'].keys())}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
