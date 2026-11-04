"""Schema create / drop helpers used by initialize_database and tests."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.database.models import Base
from src.utils.logger import get_logger

logger = get_logger(__name__)


def create_schema(engine: Engine) -> None:
    """Create all ORM tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Ensured database schema exists (%s tables)", len(Base.metadata.tables))


def drop_schema(engine: Engine) -> None:
    """Drop all ORM tables (destructive; tests / local reset only)."""
    Base.metadata.drop_all(bind=engine)
    logger.warning("Dropped all ORM tables")


def list_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        return [row[0] for row in rows]
