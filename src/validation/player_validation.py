"""Validate player identity records (Stage 9)."""

from __future__ import annotations

from typing import Any

from src.validation.issues import issue


def validate_players(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    match_id = bundle.get("match_id")
    players = bundle.get("players") or []
    seen_ids: set[str] = set()
    seen_source: set[tuple[str, str]] = set()

    for player in players:
        pid = player.get("player_id")
        if not pid:
            issues.append(
                issue(
                    code="player_missing_id",
                    message="Player row missing player_id",
                    entity_type="player",
                    match_id=match_id,
                )
            )
            continue
        if pid in seen_ids:
            issues.append(
                issue(
                    code="player_duplicate_id",
                    message=f"Duplicate player_id in match bundle: {pid}",
                    entity_type="player",
                    entity_id=pid,
                    match_id=match_id,
                )
            )
        seen_ids.add(pid)

        if not player.get("full_name") and not player.get("batting_name"):
            issues.append(
                issue(
                    code="player_missing_name",
                    message=f"Player {pid} has no full_name/batting_name",
                    severity="warning",
                    entity_type="player",
                    entity_id=pid,
                    match_id=match_id,
                )
            )

        source_name = player.get("source_name") or "ESPNcricinfo"
        source_pid = player.get("source_player_id")
        if source_pid:
            key = (source_name, str(source_pid))
            if key in seen_source:
                issues.append(
                    issue(
                        code="player_duplicate_source_identity",
                        message=f"Duplicate source identity {source_name}:{source_pid}",
                        entity_type="player",
                        entity_id=pid,
                        match_id=match_id,
                    )
                )
            seen_source.add(key)
        elif source_name == "ESPNcricinfo":
            issues.append(
                issue(
                    code="player_missing_source_id",
                    message=f"ESPNcricinfo player {pid} missing source_player_id",
                    severity="warning",
                    entity_type="player",
                    entity_id=pid,
                    match_id=match_id,
                )
            )

    # Scorecard player refs should resolve
    known = {p.get("player_id") for p in players if p.get("player_id")}
    for entity_type, rows, field in (
        ("batting_scorecard", bundle.get("batting_scorecards") or [], "player_id"),
        ("bowling_scorecard", bundle.get("bowling_scorecards") or [], "player_id"),
        ("fielding_scorecard", bundle.get("fielding_scorecards") or [], "player_id"),
    ):
        for row in rows:
            pid = row.get(field)
            if pid and known and pid not in known:
                issues.append(
                    issue(
                        code="player_scorecard_ref_missing",
                        message=f"{entity_type} references unknown player_id {pid}",
                        severity="warning",
                        entity_type="player",
                        entity_id=pid,
                        match_id=match_id,
                    )
                )

    potm = (bundle.get("match") or {}).get("player_of_match_id")
    if potm and known and potm not in known:
        issues.append(
            issue(
                code="player_of_match_not_in_players",
                message=f"player_of_match_id {potm} not in players list",
                severity="info",
                entity_type="player",
                entity_id=potm,
                match_id=match_id,
            )
        )

    return issues
