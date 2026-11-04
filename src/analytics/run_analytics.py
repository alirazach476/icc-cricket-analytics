"""Orchestrate Stage 13 analytics reports for a tournament."""

from __future__ import annotations

import json
from typing import Any

from src.analytics.advanced_metrics import (
    batting_phase_rates_from_bbb,
    bowling_economy_from_bbb,
    venue_averages,
)
from src.analytics.batting_analytics import batting_leaderboard_summary, most_boundaries
from src.analytics.bowling_analytics import bowling_leaderboard_summary
from src.analytics.duckdb_client import marts_available
from src.analytics.team_analytics import team_analytics_summary
from src.analytics.tournament_analytics import tournament_summary
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _df_records(df) -> list[dict[str, Any]]:
    return df.to_dict(orient="records")


def run_tournament_analytics(
    *,
    tournament_id: str,
    limit: int = 15,
) -> dict[str, Any]:
    if not marts_available(tournament_id=tournament_id):
        raise RuntimeError(
            "analytics_marts schema not found. Run `python scripts/run_dbt.py run` first."
        )

    started = utc_now_iso()
    report: dict[str, Any] = {
        "started_at": started,
        "tournament_id": tournament_id,
        "claims_complete_coverage": False,
        "sections": {},
    }

    report["sections"]["tournament"] = tournament_summary(tournament_id=tournament_id)
    report["sections"]["batting_leaders"] = batting_leaderboard_summary(
        tournament_id=tournament_id, limit=limit
    )
    report["sections"]["boundary_leaders"] = {
        "tournament_id": tournament_id,
        "rows": _df_records(most_boundaries(tournament_id=tournament_id, limit=limit)),
    }
    report["sections"]["bowling_leaders"] = bowling_leaderboard_summary(
        tournament_id=tournament_id, limit=limit
    )
    report["sections"]["teams"] = team_analytics_summary(tournament_id=tournament_id)
    report["sections"]["venues"] = {
        "tournament_id": tournament_id,
        "rows": _df_records(venue_averages(tournament_id=tournament_id)),
    }
    report["sections"]["bbb_batting_phases"] = batting_phase_rates_from_bbb(
        tournament_id=tournament_id
    )
    report["sections"]["bbb_bowling_economy"] = bowling_economy_from_bbb(
        tournament_id=tournament_id
    )

    report["finished_at"] = utc_now_iso()

    out_dir = ensure_dir(get_project_root() / "data" / "processed" / "analytics")
    out_path = out_dir / f"analytics_{tournament_id}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(out_path)
    logger.info("Wrote analytics report %s", out_path)
    return report
