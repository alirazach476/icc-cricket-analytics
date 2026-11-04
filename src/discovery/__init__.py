"""Discovery package: tournament registry, match discovery, source registry."""

from src.discovery.match_discovery import discover_matches
from src.discovery.source_registry import SourceRegistry, load_source_registry
from src.discovery.tournament_discovery import discover_tournaments
from src.discovery.tournament_registry import (
    EXPECTED_TOURNAMENT_IDS,
    TournamentRecord,
    TournamentRegistry,
    load_tournament_registry,
    sync_tournament_manifest,
)

__all__ = [
    "EXPECTED_TOURNAMENT_IDS",
    "SourceRegistry",
    "TournamentRecord",
    "TournamentRegistry",
    "discover_matches",
    "discover_tournaments",
    "load_source_registry",
    "load_tournament_registry",
    "sync_tournament_manifest",
]
