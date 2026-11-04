"""Clean player identity records (Stage 8).

Players are keyed by source identity. Names are never used alone to merge
distinct source ids.
"""

from __future__ import annotations

from typing import Any


def clean_player(
    player: dict[str, Any], *, source_name: str = "ESPNcricinfo"
) -> dict[str, Any] | None:
    if not player:
        return None
    player_id = player.get("player_id")
    source_player_id = player.get("source_player_id")
    full_name = (player.get("player_name") or player.get("full_name") or "").strip()
    if not player_id and source_player_id:
        prefix = "espn" if source_name == "ESPNcricinfo" else source_name.lower().replace(" ", "_")
        player_id = f"{prefix}_{source_player_id}"
    if not player_id and full_name and source_name == "Cricsheet":
        # Cricsheet deliveries use bare names — keep a namespaced id, do not merge to ESPN
        slug = "".join(ch if ch.isalnum() else "_" for ch in full_name.lower()).strip("_")
        player_id = f"cricsheet_{slug}" if slug else None
    if not player_id:
        return None
    return {
        "player_id": player_id,
        "full_name": full_name or None,
        "batting_name": (player.get("batting_name") or "").strip() or None,
        "source_name": player.get("source_name") or source_name,
        "source_player_id": str(source_player_id) if source_player_id is not None else None,
        "batting_style": player.get("batting_style"),
        "bowling_style": player.get("bowling_style"),
        "date_of_birth": player.get("date_of_birth"),
    }


def merge_player_records(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by (source_name, source_player_id) or player_id — never by name alone."""
    by_key: dict[str, dict[str, Any]] = {}
    for raw in players:
        cleaned = clean_player(raw, source_name=raw.get("source_name") or "ESPNcricinfo")
        if not cleaned:
            continue
        source_pid = cleaned.get("source_player_id")
        if source_pid:
            key = f"{cleaned['source_name']}::{source_pid}"
        else:
            key = cleaned["player_id"]
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = cleaned
            continue
        # Prefer longer / non-empty names; never change player_id
        for field in ("full_name", "batting_name"):
            old = existing.get(field) or ""
            new = cleaned.get(field) or ""
            if len(new) > len(old):
                existing[field] = cleaned[field]
        for field in ("batting_style", "bowling_style", "date_of_birth"):
            if not existing.get(field) and cleaned.get(field):
                existing[field] = cleaned[field]
    return sorted(by_key.values(), key=lambda p: p["player_id"])
