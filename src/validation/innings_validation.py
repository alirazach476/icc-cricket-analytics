"""Validate innings and scorecard row consistency (Stage 9)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.validation.issues import issue


def validate_innings(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    match_id = bundle.get("match_id")
    innings = bundle.get("innings") or []
    batting = bundle.get("batting_scorecards") or []
    bowling = bundle.get("bowling_scorecards") or []

    if not innings and bundle.get("scorecard_status") == "complete":
        issues.append(
            issue(
                code="innings_missing_for_complete_scorecard",
                message="scorecard_status=complete but no innings rows",
                entity_type="innings",
                match_id=match_id,
            )
        )
        return issues

    seen_numbers: set[int] = set()
    for inn in innings:
        innings_id = inn.get("innings_id")
        number = inn.get("innings_number")
        if number is None:
            issues.append(
                issue(
                    code="innings_missing_number",
                    message="Innings row missing innings_number",
                    entity_type="innings",
                    entity_id=innings_id,
                    match_id=match_id,
                )
            )
            continue
        number = int(number)
        if number in seen_numbers:
            issues.append(
                issue(
                    code="innings_duplicate_number",
                    message=f"Duplicate innings_number={number}",
                    entity_type="innings",
                    entity_id=innings_id,
                    match_id=match_id,
                )
            )
        seen_numbers.add(number)

        total = inn.get("total_runs")
        wickets = inn.get("wickets")
        if total is not None and int(total) < 0:
            issues.append(
                issue(
                    code="innings_negative_runs",
                    message="total_runs is negative",
                    entity_type="innings",
                    entity_id=innings_id,
                    match_id=match_id,
                )
            )
        if wickets is not None and (int(wickets) < 0 or int(wickets) > 10):
            issues.append(
                issue(
                    code="innings_wickets_out_of_range",
                    message=f"wickets={wickets} outside 0–10",
                    severity="warning",
                    entity_type="innings",
                    entity_id=innings_id,
                    match_id=match_id,
                )
            )

        if not inn.get("batting_team_id") or not inn.get("bowling_team_id"):
            issues.append(
                issue(
                    code="innings_missing_team",
                    message="Innings missing batting_team_id or bowling_team_id",
                    severity="warning",
                    entity_type="innings",
                    entity_id=innings_id,
                    match_id=match_id,
                )
            )

    # Batting runs + extras should equal innings total when all fields present
    bat_by_inn: dict[int, int] = defaultdict(int)
    for row in batting:
        inn_no = row.get("innings_number")
        if inn_no is None or row.get("runs") is None:
            continue
        bat_by_inn[int(inn_no)] += int(row["runs"])

    for inn in innings:
        inn_no = inn.get("innings_number")
        if inn_no is None or inn.get("total_runs") is None:
            continue
        inn_no = int(inn_no)
        extras = inn.get("extras")
        if extras is None:
            continue
        expected = bat_by_inn.get(inn_no, 0) + int(extras)
        actual = int(inn["total_runs"])
        if expected != actual:
            issues.append(
                issue(
                    code="innings_batting_extras_mismatch",
                    message=(
                        f"Innings {inn_no}: batting_runs({bat_by_inn.get(inn_no, 0)}) "
                        f"+ extras({extras}) = {expected} != total_runs({actual})"
                    ),
                    entity_type="innings",
                    entity_id=inn.get("innings_id"),
                    match_id=match_id,
                    details={
                        "innings_number": inn_no,
                        "batting_runs": bat_by_inn.get(inn_no, 0),
                        "extras": extras,
                        "expected": expected,
                        "actual": actual,
                    },
                )
            )

    # Bowling wickets sum should not exceed innings wickets (warn only — shared wickets etc.)
    bowl_wkts: dict[int, int] = defaultdict(int)
    for row in bowling:
        inn_no = row.get("innings_number")
        if inn_no is None or row.get("wickets") is None:
            continue
        bowl_wkts[int(inn_no)] += int(row["wickets"])
    for inn in innings:
        inn_no = inn.get("innings_number")
        if inn_no is None or inn.get("wickets") is None:
            continue
        inn_no = int(inn_no)
        if bowl_wkts.get(inn_no, 0) > int(inn["wickets"]):
            issues.append(
                issue(
                    code="innings_bowling_wickets_exceed",
                    message=(
                        f"Innings {inn_no}: bowling wickets sum {bowl_wkts[inn_no]} "
                        f"> innings wickets {inn['wickets']}"
                    ),
                    severity="warning",
                    entity_type="innings",
                    entity_id=inn.get("innings_id"),
                    match_id=match_id,
                )
            )

    return issues
