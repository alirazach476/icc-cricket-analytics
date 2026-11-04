"""PostgreSQL engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.utils.config import get_database_url
from src.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_engine(echo: bool = False) -> Engine:
    """Create a cached SQLAlchemy engine from DATABASE_URL / .env."""
    url = get_database_url()
    # Normalize SQLAlchemy URL for psycopg2
    if url.startswith("postgresql://"):
        sa_url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        sa_url = url

    engine = create_engine(
        sa_url,
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )
    logger.info("Created SQLAlchemy engine for host in DATABASE_URL")
    return engine


def get_session_factory(echo: bool = False) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(echo=echo), autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope(echo: bool = False) -> Iterator[Session]:
    """Provide a transactional session scope with commit/rollback."""
    factory = get_session_factory(echo=echo)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Return True if PostgreSQL accepts a simple query."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


def reset_engine_cache() -> None:
    """Clear cached engine (useful in tests)."""
    get_engine.cache_clear()
