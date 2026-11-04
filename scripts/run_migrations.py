"""Apply Alembic migrations to PostgreSQL."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alembic import command
from alembic.config import Config
from src.utils.config import get_database_url, get_project_root
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    root = get_project_root()
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "src" / "database" / "migrations"))
    url = get_database_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    cfg.set_main_option("sqlalchemy.url", url)

    logger.info("Running alembic upgrade head")
    command.upgrade(cfg, "head")
    print("OK - Migrations applied (alembic upgrade head).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
