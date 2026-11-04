"""Regression: syncing the match manifest must never lose rows or later-stage columns."""

from __future__ import annotations

import csv

from src.discovery.match_discovery import MATCH_MANIFEST_FIELDS, _sync_match_manifest


def _write_manifest(root, rows, extra=("ball_by_ball_status",)):
    path = root / "data" / "manifests" / "match_urls.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = MATCH_MANIFEST_FIELDS + list(extra)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(match_id, tournament_id, **extra):
    base = {f: "" for f in MATCH_MANIFEST_FIELDS}
    base.update(match_id=match_id, tournament_id=tournament_id, ball_by_ball_status="complete")
    base.update(extra)
    return base


def test_sync_with_no_new_matches_keeps_rows_and_extra_columns(tmp_path) -> None:
    path = _write_manifest(tmp_path, [_row("1", "ODI_M_2023"), _row("2", "T20_M_2024")])
    _sync_match_manifest(tmp_path, [], replace_tournaments=set())
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [r["match_id"] for r in rows] == ["1", "2"]
    assert rows[0]["ball_by_ball_status"] == "complete"
    assert not list(path.parent.glob("*.tmp"))


def test_sync_replaces_only_requested_tournament(tmp_path) -> None:
    path = _write_manifest(tmp_path, [_row("1", "ODI_M_2023"), _row("2", "T20_M_2024")])
    new = {f: "" for f in MATCH_MANIFEST_FIELDS}
    new.update(match_id="9", tournament_id="ODI_M_2023")
    _sync_match_manifest(tmp_path, [new], replace_tournaments={"ODI_M_2023"})
    rows = {r["match_id"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
    assert set(rows) == {"2", "9"}
    assert rows["2"]["ball_by_ball_status"] == "complete"
    assert rows["9"]["ball_by_ball_status"] == ""
