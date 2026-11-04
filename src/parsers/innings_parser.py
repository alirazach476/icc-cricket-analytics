"""Extract cleaned innings entities from parsed scorecard JSON (Stage 8)."""

from __future__ import annotations

from typing import Any


def parse_innings_from_scorecard(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    match_id = scorecard.get("match_id")
    rows: list[dict[str, Any]] = []
    for inn in scorecard.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        innings_number = inn.get("innings_number")
        if innings_number is None:
            continue
        innings_id = inn.get("innings_id") or f"{match_id}_{innings_number}"
        rows.append(
            {
                "innings_id": innings_id,
                "match_id": match_id or inn.get("match_id"),
                "innings_number": int(innings_number),
                "innings_type": inn.get("innings_type") or "standard",
                "batting_team_id": inn.get("batting_team_id"),
                "bowling_team_id": inn.get("bowling_team_id"),
                "total_runs": inn.get("total_runs"),
                "wickets": inn.get("wickets"),
                "overs": inn.get("overs"),
                "extras": inn.get("extras"),
                "byes": inn.get("byes"),
                "legbyes": inn.get("legbyes"),
                "wides": inn.get("wides"),
                "noballs": inn.get("noballs"),
                "penalties": inn.get("penalties"),
                "declared": bool(inn.get("declared")),
                "is_super_over": bool(inn.get("is_super_over")),
                "target": inn.get("target") or None,
                "source_name": scorecard.get("source_name") or "ESPNcricinfo",
                "source_url": scorecard.get("source_url"),
            }
        )
    rows.sort(key=lambda r: r["innings_number"])
    return rows
