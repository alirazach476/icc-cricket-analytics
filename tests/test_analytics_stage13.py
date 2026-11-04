"""Stage 13 analytics tests (requires DuckDB marts from Stage 12)."""

from __future__ import annotations

import pytest

from src.analytics.batting_analytics import top_run_scorers
from src.analytics.bowling_analytics import top_wicket_takers
from src.analytics.duckdb_client import marts_available
from src.analytics.run_analytics import run_tournament_analytics
from src.analytics.team_analytics import team_match_record
from src.analytics.tournament_analytics import tournament_coverage


pytestmark = pytest.mark.skipif(
    not marts_available(tournament_id="ODI_M_2023"),
    reason="analytics_marts not built (run dbt first)",
)


def test_top_run_scorers_odi_2023() -> None:
    df = top_run_scorers(tournament_id="ODI_M_2023", limit=5)
    assert len(df) == 5
    assert df.iloc[0]["runs"] >= df.iloc[1]["runs"]
    assert df.iloc[0]["player_name"]


def test_top_wicket_takers_odi_2023() -> None:
    df = top_wicket_takers(tournament_id="ODI_M_2023", limit=5)
    assert len(df) == 5
    assert df.iloc[0]["wickets"] >= df.iloc[1]["wickets"]


def test_team_records_and_coverage() -> None:
    teams = team_match_record(tournament_id="ODI_M_2023")
    assert len(teams) == 10
    assert teams["wins"].sum() > 0
    cov = tournament_coverage(tournament_id="ODI_M_2023")
    assert int(cov.iloc[0]["matches_loaded"]) == 48
    assert bool(cov.iloc[0]["claims_complete_coverage"]) is False


def test_run_tournament_analytics_writes_report() -> None:
    report = run_tournament_analytics(tournament_id="ODI_M_2023", limit=10)
    assert report["claims_complete_coverage"] is False
    assert report["sections"]["batting_leaders"]["row_count"] == 10
    assert report["sections"]["bowling_leaders"]["row_count"] == 10
    assert report["sections"]["bbb_batting_phases"]["status"] == "ok"
    from pathlib import Path

    assert Path(report["report_path"]).exists()
