"""Extract batting scorecard rows from parsed scorecard JSON (Stage 8)."""

from __future__ import annotations

from typing import Any


def parse_batting_from_scorecard(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    match_id = scorecard.get("match_id")
    rows: list[dict[str, Any]] = []
    for row in scorecard.get("batting_scorecards") or []:
        if not isinstance(row, dict) or not row.get("player_id"):
            continue
        innings_number = row.get("innings_number")
        rows.append(
            {
                "match_id": match_id or row.get("match_id"),
                "innings_id": f"{match_id}_{innings_number}" if match_id and innings_number else None,
                "innings_number": innings_number,
                "player_id": row["player_id"],
                "player_name": row.get("player_name"),
                "team_id": row.get("team_id"),
                "batting_position": row.get("batting_position"),
                "runs": row.get("runs"),
                "balls_faced": row.get("balls_faced"),
                "fours": row.get("fours"),
                "sixes": row.get("sixes"),
                "strike_rate": row.get("strike_rate"),
                "dismissal": row.get("dismissal"),
                "dismissal_type": row.get("dismissal_type"),
                "dismissed_by": row.get("dismissed_by"),
                "fielder": row.get("fielder"),
                "is_out": bool(row.get("is_out")),
                "source_name": scorecard.get("source_name") or "ESPNcricinfo",
                "source_url": scorecard.get("source_url"),
            }
        )
    return rows
