"""Extract cleaned match entities from parsed scorecard JSON (Stage 8)."""

from __future__ import annotations

from typing import Any

from src.transformations.clean_matches import clean_match


def parse_match_from_scorecard(
    scorecard: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    ball_by_ball_status: str | None = None,
) -> dict[str, Any] | None:
    return clean_match(
        scorecard.get("match"),
        tournament_id=scorecard.get("tournament_id"),
        manifest=manifest,
        scorecard_status=scorecard.get("scorecard_status"),
        ball_by_ball_status=ball_by_ball_status,
    )
