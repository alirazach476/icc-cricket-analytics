"""Clean match records from parsed scorecards (Stage 8)."""

from __future__ import annotations

from typing import Any

from src.transformations.standardize_teams import canonical_team_name

# ESPNcricinfo tossWinnerChoice: 1 = bat, 2 = field (observed on modern pages).
TOSS_DECISION_MAP = {
    1: "bat",
    2: "field",
    "1": "bat",
    "2": "field",
    "bat": "bat",
    "field": "field",
    "bowl": "field",
}


def clean_match(
    match: dict[str, Any] | None,
    *,
    tournament_id: str | None = None,
    manifest: dict[str, Any] | None = None,
    scorecard_status: str | None = None,
    ball_by_ball_status: str | None = None,
) -> dict[str, Any] | None:
    """Normalize a match dict. Returns None if input is empty (never fabricates)."""
    if not match:
        return None

    toss_raw = match.get("toss_decision")
    toss_decision = TOSS_DECISION_MAP.get(toss_raw, None)
    if toss_decision is None and isinstance(toss_raw, str) and toss_raw.strip():
        toss_decision = toss_raw.strip().lower()

    manifest = manifest or {}
    cleaned = {
        "match_id": str(match.get("match_id") or manifest.get("match_id") or ""),
        "tournament_id": tournament_id
        or match.get("tournament_id")
        or manifest.get("tournament_id"),
        "source_match_id": match.get("source_match_id") or match.get("match_id"),
        "match_number": _int_or_none(manifest.get("match_number") or match.get("match_number")),
        "match_stage": manifest.get("match_stage")
        or match.get("match_stage")
        or match.get("title"),
        "match_date": (match.get("match_date") or manifest.get("match_date") or "")[:10] or None,
        "start_time": match.get("start_time"),
        "venue": _strip(match.get("venue") or manifest.get("venue")),
        "city": _strip(match.get("city") or manifest.get("city")),
        "team1_id": match.get("team1_id"),
        "team2_id": match.get("team2_id"),
        "team1_name": canonical_team_name(manifest.get("team1_name")),
        "team2_name": canonical_team_name(manifest.get("team2_name")),
        "toss_winner_id": match.get("toss_winner_id"),
        "toss_decision": toss_decision,
        "winner_id": match.get("winner_id"),
        "result_type": match.get("result_type") or manifest.get("result_type"),
        "result_margin": match.get("result_margin") or manifest.get("result_margin"),
        "player_of_match_id": match.get("player_of_match_id"),
        "umpires": match.get("umpires"),
        "match_referee": match.get("match_referee"),
        "scorecard_url": manifest.get("scorecard_url") or match.get("source_url"),
        "commentary_url": manifest.get("commentary_url"),
        "is_cancelled": bool(match.get("is_cancelled") or _truthy(manifest.get("is_cancelled"))),
        "is_super_over": bool(match.get("is_super_over") or _truthy(manifest.get("is_super_over"))),
        "match_status": match.get("status") or match.get("match_status"),
        "scorecard_status": scorecard_status or match.get("scorecard_status") or "not_checked",
        "ball_by_ball_status": ball_by_ball_status
        or match.get("ball_by_ball_status")
        or manifest.get("ball_by_ball_status")
        or "not_checked",
        "source_name": match.get("source_name") or "ESPNcricinfo",
        "source_url": match.get("source_url") or manifest.get("scorecard_url"),
    }
    if not cleaned["match_id"]:
        return None
    return cleaned


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}
