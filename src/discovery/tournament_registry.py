"""Tournament registry — config-driven, validated, duplicate-safe.

Stage 2: load YAML, validate with Pydantic, enforce scope rules, sync manifests.
New editions are added by editing config/tournaments.yaml only (no pipeline code changes).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from src.utils.config import get_project_root
from src.utils.helpers import utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

EXPECTED_TOURNAMENT_IDS: frozenset[str] = frozenset(
    {
        "ODI_M_2003",
        "ODI_M_2007",
        "ODI_M_2011",
        "ODI_M_2015",
        "ODI_M_2019",
        "ODI_M_2023",
        "T20_M_2007",
        "T20_M_2009",
        "T20_M_2010",
        "T20_M_2012",
        "T20_M_2014",
        "T20_M_2016",
        "T20_M_2021",
        "T20_M_2022",
        "T20_M_2024",
        "T20_M_2026",
    }
)

CollectionStatus = Literal[
    "not_started",
    "discovering",
    "collecting",
    "partial",
    "complete",
    "failed",
]

CompletionStatus = Literal[
    "scheduled",
    "in_progress",
    "completed",
    "cancelled",
    "unknown",
]


class MatchFormat(str, Enum):
    ODI = "ODI"
    T20 = "T20"


class TournamentRecord(BaseModel):
    """Single tournament edition in the registry."""

    tournament_id: str = Field(..., min_length=5, max_length=32)
    tournament_name: str = Field(..., min_length=3)
    year: int = Field(..., ge=2003, le=2026)
    format: MatchFormat
    gender: Literal["Men"] = "Men"
    host_country: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    winner: str | None = None
    runner_up: str | None = None
    number_of_teams: int | None = Field(default=None, ge=2, le=40)
    number_of_matches: int | None = Field(default=None, ge=1, le=200)
    source_url: HttpUrl | str | None = None
    collection_status: CollectionStatus = "not_started"
    completion_status: CompletionStatus = "unknown"
    metadata_notes: str | None = None
    notes: str | None = None

    @field_validator("tournament_id")
    @classmethod
    def validate_tournament_id(cls, value: str) -> str:
        if value not in EXPECTED_TOURNAMENT_IDS:
            raise ValueError(
                f"tournament_id '{value}' is outside the allowed men's ODI/T20 World Cup scope"
            )
        return value

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        # YYYY-MM-DD only; full calendar validation deferred to discovery enrichment
        parts = value.split("-")
        if len(parts) != 3 or len(parts[0]) != 4:
            raise ValueError(f"Date must be YYYY-MM-DD, got: {value}")
        return value

    @model_validator(mode="after")
    def validate_id_matches_year_format(self) -> TournamentRecord:
        expected_prefix = f"{self.format.value}_M_{self.year}"
        if self.tournament_id != expected_prefix:
            raise ValueError(
                f"tournament_id '{self.tournament_id}' must equal '{expected_prefix}'"
            )
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.completion_status != "completed":
            # Incomplete tournaments must not claim winners as final unless completed
            if self.winner or self.runner_up:
                logger.warning(
                    "%s has winner/runner_up but completion_status=%s",
                    self.tournament_id,
                    self.completion_status,
                )
        return self

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "tournament_id": self.tournament_id,
            "tournament_name": self.tournament_name,
            "year": self.year,
            "format": self.format.value,
            "gender": self.gender,
            "host_country": self.host_country or "",
            "start_date": self.start_date or "",
            "end_date": self.end_date or "",
            "winner": self.winner or "",
            "runner_up": self.runner_up or "",
            "number_of_teams": self.number_of_teams
            if self.number_of_teams is not None
            else "",
            "number_of_matches": self.number_of_matches
            if self.number_of_matches is not None
            else "",
            "source_url": str(self.source_url) if self.source_url else "",
            "collection_status": self.collection_status,
            "completion_status": self.completion_status,
        }


class TournamentRegistry(BaseModel):
    """Validated registry of in-scope tournament editions."""

    registry_version: str = "0.2.0"
    tournaments: list[TournamentRecord]

    @model_validator(mode="after")
    def validate_unique_and_complete_scope(self) -> TournamentRegistry:
        ids = [t.tournament_id for t in self.tournaments]
        duplicates = sorted({tid for tid in ids if ids.count(tid) > 1})
        if duplicates:
            raise ValueError(f"Duplicate tournament_id values: {duplicates}")

        found = set(ids)
        missing = sorted(EXPECTED_TOURNAMENT_IDS - found)
        unexpected = sorted(found - EXPECTED_TOURNAMENT_IDS)
        if missing:
            raise ValueError(f"Registry missing required tournament_ids: {missing}")
        if unexpected:
            raise ValueError(f"Registry contains out-of-scope tournament_ids: {unexpected}")
        if len(self.tournaments) != 16:
            raise ValueError(f"Expected 16 tournaments, found {len(self.tournaments)}")
        return self

    def get(self, tournament_id: str) -> TournamentRecord:
        for tournament in self.tournaments:
            if tournament.tournament_id == tournament_id:
                return tournament
        raise KeyError(f"Unknown tournament_id: {tournament_id}")

    def by_format(self, match_format: str | MatchFormat) -> list[TournamentRecord]:
        fmt = MatchFormat(match_format) if isinstance(match_format, str) else match_format
        return [t for t in self.tournaments if t.format == fmt]

    def by_year(self, year: int) -> list[TournamentRecord]:
        return [t for t in self.tournaments if t.year == year]

    def summary(self) -> dict[str, Any]:
        return {
            "registry_version": self.registry_version,
            "total": len(self.tournaments),
            "odi": len(self.by_format(MatchFormat.ODI)),
            "t20": len(self.by_format(MatchFormat.T20)),
            "completed": sum(1 for t in self.tournaments if t.completion_status == "completed"),
            "with_source_url": sum(1 for t in self.tournaments if t.source_url),
            "match_counts_verified": sum(
                1 for t in self.tournaments if t.number_of_matches is not None
            ),
            "generated_at": utc_now_iso(),
        }


def _registry_yaml_path(root: Path | None = None) -> Path:
    base = root or get_project_root()
    return base / "config" / "tournaments.yaml"


def load_tournament_registry(path: Path | None = None) -> TournamentRegistry:
    """Load and validate the YAML tournament registry."""
    yaml_path = path or _registry_yaml_path()
    with yaml_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid registry YAML structure: {yaml_path}")

    tournaments = raw.get("tournaments")
    if not isinstance(tournaments, list):
        raise ValueError("tournaments.yaml must contain a 'tournaments' list")

    registry = TournamentRegistry(
        registry_version=str(raw.get("registry_version", "0.2.0")),
        tournaments=tournaments,
    )
    logger.info(
        "Loaded tournament registry v%s (%s editions)",
        registry.registry_version,
        len(registry.tournaments),
    )
    return registry


def sync_tournament_manifest(
    registry: TournamentRegistry | None = None,
    *,
    root: Path | None = None,
) -> Path:
    """Write validated registry rows to data/manifests/tournaments.csv."""
    base = root or get_project_root()
    registry = registry or load_tournament_registry()
    manifest_path = base / "data" / "manifests" / "tournaments.csv"
    fieldnames = [
        "tournament_id",
        "tournament_name",
        "year",
        "format",
        "gender",
        "host_country",
        "start_date",
        "end_date",
        "winner",
        "runner_up",
        "number_of_teams",
        "number_of_matches",
        "source_url",
        "collection_status",
        "completion_status",
    ]

    rows = [t.to_manifest_row() for t in registry.tournaments]
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Synced %s tournaments to %s", len(rows), manifest_path)
    return manifest_path


def iter_source_urls(registry: TournamentRegistry | None = None) -> Iterable[tuple[str, str]]:
    """Yield (tournament_id, source_url) for editions with a URL."""
    registry = registry or load_tournament_registry()
    for tournament in registry.tournaments:
        if tournament.source_url:
            yield tournament.tournament_id, str(tournament.source_url)
