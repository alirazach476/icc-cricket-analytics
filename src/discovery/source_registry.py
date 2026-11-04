"""Source registry — primary and supplementary data sources with attribution rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from src.utils.config import load_source_rules
from src.utils.logger import get_logger

logger = get_logger(__name__)

SourcePrecedence = Literal["primary", "supplementary"]


class DataSource(BaseModel):
    """A named external data source used by collectors."""

    name: str
    base_url: HttpUrl | str
    precedence: SourcePrecedence
    attribution_required: bool = True
    use_when: str | None = None
    rules: list[str] = Field(default_factory=list)


class SourceRegistry(BaseModel):
    """Validated view of config/source_rules.yaml."""

    primary: DataSource
    supplementary: list[DataSource] = Field(default_factory=list)
    respect_robots: bool = True
    min_delay_seconds: float = 1.5
    max_retries: int = 3
    never_overwrite_raw: bool = True
    stop_on_http_status: list[int] = Field(default_factory=lambda: [401, 403, 429])

    def get(self, name: str) -> DataSource:
        if self.primary.name.lower() == name.lower():
            return self.primary
        for source in self.supplementary:
            if source.name.lower() == name.lower():
                return source
        raise KeyError(f"Unknown data source: {name}")

    def attribution_line(self, source_name: str, source_url: str | None = None) -> str:
        source = self.get(source_name)
        suffix = f" URL: {source_url}" if source_url else ""
        return f"Source: {source.name} ({source.precedence}){suffix}"


def load_source_registry(rules: dict[str, Any] | None = None) -> SourceRegistry:
    """Build SourceRegistry from source_rules.yaml (or provided dict)."""
    raw = rules if rules is not None else load_source_rules()
    primary_raw = raw["primary_source"]
    supplementary_raw = raw.get("supplementary_sources") or []

    primary = DataSource(
        name=primary_raw["name"],
        base_url=primary_raw["base_url"],
        precedence="primary",
        attribution_required=bool(primary_raw.get("attribution_required", True)),
        rules=list(primary_raw.get("rules") or []),
    )
    supplementary = [
        DataSource(
            name=item["name"],
            base_url=item["base_url"],
            precedence="supplementary",
            attribution_required=bool(item.get("attribution_required", True)),
            use_when=item.get("use_when"),
            rules=list(item.get("rules") or []),
        )
        for item in supplementary_raw
    ]

    rate = raw.get("rate_limiting") or {}
    robots = raw.get("robots") or {}
    caching = raw.get("caching") or {}

    registry = SourceRegistry(
        primary=primary,
        supplementary=supplementary,
        respect_robots=bool(robots.get("respect", True)),
        min_delay_seconds=float(rate.get("min_delay_seconds", 1.5)),
        max_retries=int(rate.get("max_retries", 3)),
        never_overwrite_raw=bool(caching.get("never_overwrite_raw", True)),
        stop_on_http_status=list(rate.get("stop_on_http_status") or [401, 403, 429]),
    )
    logger.info(
        "Loaded source registry: primary=%s supplementary=%s",
        registry.primary.name,
        [s.name for s in registry.supplementary],
    )
    return registry
