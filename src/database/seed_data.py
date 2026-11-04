"""Seed reference data: sources + tournament registry rows."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.database.repository import (
    list_tournaments,
    tournament_payload_from_registry,
    upsert_source,
    upsert_tournaments,
)
from src.discovery.source_registry import load_source_registry
from src.discovery.tournament_registry import load_tournament_registry
from src.utils.logger import get_logger

logger = get_logger(__name__)


def seed_sources(session: Session) -> dict[str, int]:
    """Upsert primary/supplementary sources; return name -> source_id."""
    registry = load_source_registry()
    mapping: dict[str, int] = {}

    primary = upsert_source(
        session,
        name=registry.primary.name,
        base_url=str(registry.primary.base_url),
        precedence=registry.primary.precedence,
        attribution_required=registry.primary.attribution_required,
        notes="; ".join(registry.primary.rules[:3]) if registry.primary.rules else None,
    )
    mapping[primary.name] = primary.source_id

    for source in registry.supplementary:
        row = upsert_source(
            session,
            name=source.name,
            base_url=str(source.base_url),
            precedence=source.precedence,
            attribution_required=source.attribution_required,
            notes=source.use_when,
        )
        mapping[row.name] = row.source_id

    logger.info("Seeded sources: %s", sorted(mapping))
    return mapping


def seed_tournaments(session: Session, source_id: int | None = None) -> int:
    """Upsert all 16 registry tournaments. Does not invent match rows."""
    registry = load_tournament_registry()
    payloads = [
        tournament_payload_from_registry(record, source_id=source_id)
        for record in registry.tournaments
    ]
    # Ensure collected_at is timezone-aware
    now = datetime.now(UTC)
    for payload in payloads:
        payload["collected_at"] = now
    return upsert_tournaments(session, payloads)


def seed_reference_data(session: Session) -> dict[str, object]:
    """Seed sources and tournaments inside an open transaction."""
    source_ids = seed_sources(session)
    espn_id = source_ids.get("ESPNcricinfo")
    tournament_count = seed_tournaments(session, source_id=espn_id)
    tournaments = list_tournaments(session)
    return {
        "sources": source_ids,
        "tournament_count": tournament_count,
        "tournament_ids": [t.tournament_id for t in tournaments],
        "seeded_at": datetime.now(UTC).isoformat(),
    }
