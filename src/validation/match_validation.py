"""Validate normalized match records (Stage 9)."""

from __future__ import annotations

from typing import Any

from src.validation.issues import issue

REQUIRED_MATCH_FIELDS = (
    "match_id",
    "tournament_id",
    "match_date",
    "team1_id",
    "team2_id",
)

VALID_SCORECARD_STATUS = {"complete", "partial", "missing", "not_checked"}
VALID_BBB_STATUS = {"complete", "partial", "unavailable", "not_checked"}
VALID_TOSS = {None, "bat", "field"}


def validate_match(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a normalized match bundle's match entity and top-level status."""
    issues: list[dict[str, Any]] = []
    match_id = bundle.get("match_id")
    match = bundle.get("match") or {}

    if not match:
        issues.append(
            issue(
                code="match_missing",
                message="Normalized bundle has no match object",
                entity_type="match",
                match_id=match_id,
            )
        )
        return issues

    for field in REQUIRED_MATCH_FIELDS:
        if not match.get(field):
            issues.append(
                issue(
                    code="match_required_field",
                    message=f"Missing required match field: {field}",
                    entity_type="match",
                    entity_id=match_id,
                    match_id=match_id,
                    details={"field": field},
                )
            )

    if match.get("team1_id") and match.get("team2_id") and match["team1_id"] == match["team2_id"]:
        issues.append(
            issue(
                code="match_same_teams",
                message="team1_id and team2_id are identical",
                entity_type="match",
                entity_id=match_id,
                match_id=match_id,
            )
        )

    team_ids = {t.get("team_id") for t in (bundle.get("teams") or []) if t.get("team_id")}
    for side in ("team1_id", "team2_id", "toss_winner_id", "winner_id"):
        tid = match.get(side)
        if tid and team_ids and tid not in team_ids:
            # winner/toss may still be valid ESPN ids even if teams list incomplete
            severity = "warning" if side in {"toss_winner_id", "winner_id"} else "error"
            issues.append(
                issue(
                    code="match_team_ref_unknown",
                    message=f"{side}={tid} not present in bundle teams",
                    severity=severity,
                    entity_type="match",
                    entity_id=match_id,
                    match_id=match_id,
                    details={"field": side, "team_id": tid},
                )
            )

    sc_status = bundle.get("scorecard_status") or match.get("scorecard_status")
    if sc_status not in VALID_SCORECARD_STATUS:
        issues.append(
            issue(
                code="match_invalid_scorecard_status",
                message=f"Invalid scorecard_status: {sc_status}",
                entity_type="match",
                entity_id=match_id,
                match_id=match_id,
            )
        )

    bbb_status = bundle.get("ball_by_ball_status") or match.get("ball_by_ball_status")
    if bbb_status not in VALID_BBB_STATUS:
        issues.append(
            issue(
                code="match_invalid_bbb_status",
                message=f"Invalid ball_by_ball_status: {bbb_status}",
                entity_type="match",
                entity_id=match_id,
                match_id=match_id,
            )
        )

    toss = match.get("toss_decision")
    if toss not in VALID_TOSS:
        issues.append(
            issue(
                code="match_invalid_toss_decision",
                message=f"Unrecognized toss_decision: {toss}",
                severity="warning",
                entity_type="match",
                entity_id=match_id,
                match_id=match_id,
            )
        )

    if match.get("is_cancelled") and match.get("winner_id"):
        issues.append(
            issue(
                code="match_cancelled_has_winner",
                message="Cancelled match has a winner_id",
                severity="warning",
                entity_type="match",
                entity_id=match_id,
                match_id=match_id,
            )
        )

    date = match.get("match_date") or ""
    if date and len(date) >= 10:
        try:
            year = int(date[:4])
            if year < 2003 or year > 2026:
                issues.append(
                    issue(
                        code="match_date_out_of_scope",
                        message=f"match_date year {year} outside project scope 2003–2026",
                        severity="warning",
                        entity_type="match",
                        entity_id=match_id,
                        match_id=match_id,
                    )
                )
        except ValueError:
            issues.append(
                issue(
                    code="match_date_unparseable",
                    message=f"Could not parse match_date: {date}",
                    entity_type="match",
                    entity_id=match_id,
                    match_id=match_id,
                )
            )

    return issues
