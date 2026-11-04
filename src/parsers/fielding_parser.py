"""Extract fielding scorecard rows from parsed scorecard JSON (Stage 8)."""

from __future__ import annotations

from typing import Any


def parse_fielding_from_scorecard(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    match_id = scorecard.get("match_id")
    rows: list[dict[str, Any]] = []
    for row in scorecard.get("fielding_scorecards") or []:
        if not isinstance(row, dict) or not row.get("player_id"):
            continue
        rows.append(
            {
                "match_id": match_id or row.get("match_id"),
                "player_id": row["player_id"],
                "player_name": row.get("player_name"),
                "team_id": row.get("team_id"),
                "catches": int(row.get("catches") or 0),
                "run_outs": int(row.get("run_outs") or 0),
                "stumpings": int(row.get("stumpings") or 0),
                "source_name": scorecard.get("source_name") or "ESPNcricinfo",
                "source_url": scorecard.get("source_url"),
            }
        )
    return rows
