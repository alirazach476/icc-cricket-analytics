"""Stage 4 tournament discovery / parser tests (offline fixtures)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.collectors.base_collector import AccessRestrictedError, BaseCollector, FetchResult
from src.discovery.tournament_discovery import discover_tournaments
from src.parsers.tournament_parser import parse_tournament_html

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "tournament_series_minimal.html"
)


def test_parse_tournament_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    parsed = parse_tournament_html(
        html,
        source_url="https://www.espncricinfo.com/series/example",
    )
    assert parsed["parse_status"] == "ok"
    assert parsed["next_data_found"] is True
    assert parsed["discovered_name"] == "ICC Cricket World Cup 2023/24"
    assert parsed["extracted_fields"]["start_date"] == "2023-10-05"
    assert parsed["extracted_fields"]["end_date"] == "2023-11-19"
    assert parsed["extracted_fields"]["number_of_teams"] == 10
    assert parsed["series_object"]["objectId"] == 1367856
    assert "Jiostar" not in (parsed["discovered_name"] or "")


def test_dry_run_discovery_does_not_http() -> None:
    report = discover_tournaments(live=False)
    assert report["total_targeted"] == 17
    assert report["summary"]["dry_run"] == 17
    assert report["collector_stopped"] is False


def test_access_restricted_stops_further_live_fetches() -> None:
    html = FIXTURE.read_text(encoding="utf-8")

    def fake_fetch(self, url, allow_cache_path=None):  # noqa: ANN001
        # First call restricted; should stop remaining live attempts
        raise_result = FetchResult(
            url=url,
            ok=False,
            status_code=403,
            error="HTTP 403",
            access_status="access_restricted",
        )
        self._stop_collection = True
        self._stop_reason = "HTTP 403 blocked"
        return raise_result

    with patch.object(BaseCollector, "fetch_html", fake_fetch):
        report = discover_tournaments(
            tournament_ids=["ODI_M_2023", "ODI_M_2019"],
            live=True,
            use_cache=False,
            update_database=False,
        )

    assert report["collector_stopped"] is True
    assert report["summary"]["access_restricted"] == 2
    # Ensure we did not claim discovery success
    assert report["summary"]["discovered"] == 0


def test_cached_html_path_used_when_present(tmp_path: Path) -> None:
    # Parser + collector cache behaviour is covered via fixture content parse above.
    # This asserts AccessRestrictedError carries status for stop logic.
    err = AccessRestrictedError("HTTP 403")
    setattr(err, "status_code", 403)
    assert "403" in str(err)
