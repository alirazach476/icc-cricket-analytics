"""Extract bowling scorecard rows from parsed scorecard JSON (Stage 8)."""

from __future__ import annotations

from typing import Any


def parse_bowling_from_scorecard(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    match_id = scorecard.get("match_id")
    rows: list[dict[str, Any]] = []
    for row in scorecard.get("bowling_scorecards") or []:
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
                "overs": row.get("overs"),
                "maidens": row.get("maidens"),
                "runs_conceded": row.get("runs_conceded"),
                "wickets": row.get("wickets"),
                "economy": row.get("economy"),
                "dots": row.get("dots"),
                "wides": row.get("wides"),
                "no_balls": row.get("no_balls"),
                "source_name": scorecard.get("source_name") or "ESPNcricinfo",
                "source_url": scorecard.get("source_url"),
            }
        )
    return rows
