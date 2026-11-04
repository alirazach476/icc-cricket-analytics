"""Lightweight derived stats for normalized matches (Stage 8; deeper analytics in Stage 13)."""

from __future__ import annotations

from typing import Any


def match_scorecard_totals(bundle: dict[str, Any]) -> dict[str, Any]:
    """Summarize totals already present in a normalized match bundle — no fabrication."""
    innings = bundle.get("innings") or []
    batting = bundle.get("batting_scorecards") or []
    return {
        "match_id": bundle.get("match_id"),
        "innings_count": len(innings),
        "batting_rows": len(batting),
        "bowling_rows": len(bundle.get("bowling_scorecards") or []),
        "fielding_rows": len(bundle.get("fielding_scorecards") or []),
        "delivery_count": bundle.get("delivery_count") or 0,
        "innings_runs": [
            {
                "innings_number": inn.get("innings_number"),
                "total_runs": inn.get("total_runs"),
                "wickets": inn.get("wickets"),
            }
            for inn in innings
        ],
        "batting_runs_sum": sum(
            int(r.get("runs") or 0) for r in batting if r.get("runs") is not None
        ),
    }
