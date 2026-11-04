"""Canonical team naming for World Cup sides (Stage 8).

Does not invent teams. Maps known aliases onto a stable display name while
preserving source team ids from ESPNcricinfo when present.
"""

from __future__ import annotations

import re
from typing import Any

# Aliases observed across ESPN / Cricsheet — values are canonical long names.
TEAM_ALIASES: dict[str, str] = {
    "uae": "United Arab Emirates",
    "u a e": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "west indies": "West Indies",
    "wi": "West Indies",
    "south africa": "South Africa",
    "sa": "South Africa",
    "new zealand": "New Zealand",
    "nz": "New Zealand",
    "sri lanka": "Sri Lanka",
    "sl": "Sri Lanka",
    "england": "England",
    "eng": "England",
    "australia": "Australia",
    "aus": "Australia",
    "india": "India",
    "ind": "India",
    "pakistan": "Pakistan",
    "pak": "Pakistan",
    "bangladesh": "Bangladesh",
    "ban": "Bangladesh",
    "afghanistan": "Afghanistan",
    "afg": "Afghanistan",
    "netherlands": "Netherlands",
    "ned": "Netherlands",
    "holland": "Netherlands",
    "ireland": "Ireland",
    "ire": "Ireland",
    "scotland": "Scotland",
    "sco": "Scotland",
    "zimbabwe": "Zimbabwe",
    "zim": "Zimbabwe",
    "kenya": "Kenya",
    "ken": "Kenya",
    "canada": "Canada",
    "can": "Canada",
    "namibia": "Namibia",
    "nam": "Namibia",
    "bermuda": "Bermuda",
    "ber": "Bermuda",
    "usa": "United States of America",
    "united states": "United States of America",
    "united states of america": "United States of America",
    "papua new guinea": "Papua New Guinea",
    "png": "Papua New Guinea",
    "nepal": "Nepal",
    "oman": "Oman",
    "hong kong": "Hong Kong",
}


def _key(name: str | None) -> str:
    if not name:
        return ""
    cleaned = name.strip().lower().replace("&", "and")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def canonical_team_name(name: str | None) -> str | None:
    """Return canonical team name, or the trimmed original if unknown (never fabricate)."""
    if name is None:
        return None
    stripped = name.strip()
    if not stripped:
        return None
    mapped = TEAM_ALIASES.get(_key(stripped))
    return mapped or stripped


def standardize_team_record(team: dict[str, Any]) -> dict[str, Any]:
    """Normalize a team dict extracted from scorecard parse output."""
    raw_name = team.get("team_name") or team.get("name")
    canonical = canonical_team_name(raw_name)
    team_id = team.get("team_id")
    source_team_id = team.get("source_team_id")
    if not team_id and source_team_id:
        team_id = f"espn_{source_team_id}"
    return {
        "team_id": team_id,
        "team_name": canonical,
        "short_name": team.get("abbreviation") or team.get("short_name"),
        "source_team_id": str(source_team_id) if source_team_id is not None else None,
        "source_name": team.get("source_name") or "ESPNcricinfo",
        "raw_team_name": raw_name,
    }
