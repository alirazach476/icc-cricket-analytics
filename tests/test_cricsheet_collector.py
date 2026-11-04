"""Stage 7 Cricsheet linking tests (no network)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.collectors.cricsheet_collector import CricsheetCollector
from src.parsers.ball_by_ball_parser import normalize_team_name


def test_find_candidates_and_load_deliveries(tmp_path: Path, monkeypatch) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "cricsheet_match_minimal.json"
    extract = tmp_path / "odi"
    extract.mkdir()
    shutil.copy(fixture, extract / "1384392.json")

    collector = CricsheetCollector()
    monkeypatch.setattr(collector, "base_dir", tmp_path)
    monkeypatch.setattr(collector, "download_bundle", lambda match_format, force=False: extract)
    monkeypatch.setattr(collector, "project_root", tmp_path)

    candidates = collector.find_candidates(
        match_format="ODI",
        match_date="2023-10-05",
        team1="England",
        team2="New Zealand",
    )
    assert len(candidates) == 1
    assert candidates[0]["teams_norm"] == sorted(
        [normalize_team_name("England"), normalize_team_name("New Zealand")]
    )

    result = collector.load_deliveries_for_match(
        match_id="1384392",
        match_format="ODI",
        match_date="2023-10-05",
        team1="England",
        team2="New Zealand",
    )
    assert result["access_status"] == "ok"
    assert result["parse"]["ball_by_ball_status"] == "complete"
    assert result["parse"]["delivery_count"] == 5
    out = Path(result["parsed_json_path"])
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["linked_cricsheet_file"] == "1384392.json"


def test_ambiguous_candidates_refused(tmp_path: Path, monkeypatch) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "cricsheet_match_minimal.json"
    extract = tmp_path / "odi"
    extract.mkdir()
    for name in ("a.json", "b.json"):
        shutil.copy(fixture, extract / name)

    collector = CricsheetCollector()
    monkeypatch.setattr(collector, "base_dir", tmp_path)
    monkeypatch.setattr(collector, "download_bundle", lambda match_format, force=False: extract)

    result = collector.load_deliveries_for_match(
        match_id="1384392",
        match_format="ODI",
        match_date="2023-10-05",
        team1="England",
        team2="New Zealand",
    )
    assert result["access_status"] == "ambiguous"
    assert result["parse"] is None
    assert "Multiple" in (result["error"] or "")
