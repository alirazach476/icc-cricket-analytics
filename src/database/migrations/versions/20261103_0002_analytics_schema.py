"""Analytics (gold) star schema in the ``analytics`` Postgres schema (Stage 5).

Revision ID: 20261103_0002
Revises: 20261103_0001
Create Date: 2026-11-03

The DDL is generated from ``src/warehouse/analytics_schema.py`` into
``sql/schema/analytics_schema.sql`` (``python scripts/load_warehouse.py`` rewrites it). It is
idempotent (``IF NOT EXISTS``), so applying it to a database that already has the schema is safe.
Data is loaded separately by ``scripts/load_warehouse.py``; this revision creates structure only.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "20261103_0002"
down_revision: str | None = "20261103_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = Path(__file__).resolve().parents[4] / "sql" / "schema" / "analytics_schema.sql"


def upgrade() -> None:
    sql = DDL.read_text(encoding="utf-8")
    for stmt in (s.strip() for s in sql.split(";\n")):
        # Skip empty chunks and the comment-only header.
        body = "\n".join(ln for ln in stmt.splitlines() if not ln.strip().startswith("--")).strip()
        if body:
            op.execute(body)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
