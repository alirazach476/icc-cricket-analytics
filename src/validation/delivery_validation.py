"""Validate ball-by-ball delivery records (Stage 9)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.validation.issues import issue


def validate_deliveries(
    bundle: dict[str, Any],
    *,
    deliveries_doc: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    match_id = bundle.get("match_id")
    bbb_status = bundle.get("ball_by_ball_status") or "not_checked"
    deliveries = list((deliveries_doc or {}).get("deliveries") or [])
    if not deliveries and bundle.get("delivery_count"):
        # Bundle may omit full deliveries; count alone is informational
        pass

    if bbb_status == "complete" and not deliveries:
        issues.append(
            issue(
                code="deliveries_missing_for_complete_bbb",
                message="ball_by_ball_status=complete but no delivery rows loaded",
                entity_type="delivery",
                match_id=match_id,
            )
        )
        return issues

    if bbb_status in {"unavailable", "not_checked"} and deliveries:
        issues.append(
            issue(
                code="deliveries_present_but_status_not_complete",
                message=f"Found {len(deliveries)} deliveries while status={bbb_status}",
                severity="warning",
                entity_type="delivery",
                match_id=match_id,
            )
        )

    seen_seq: set[tuple[int, int]] = set()
    seen_ids: set[str] = set()
    runs_by_inn: dict[int, int] = defaultdict(int)
    wkts_by_inn: dict[int, int] = defaultdict(int)

    for d in deliveries:
        inn_no = d.get("innings_number")
        seq = d.get("delivery_sequence")
        did = d.get("delivery_id")
        if inn_no is None or seq is None:
            issues.append(
                issue(
                    code="delivery_missing_keys",
                    message="Delivery missing innings_number or delivery_sequence",
                    entity_type="delivery",
                    entity_id=did,
                    match_id=match_id,
                )
            )
            continue
        key = (int(inn_no), int(seq))
        if key in seen_seq:
            issues.append(
                issue(
                    code="delivery_duplicate_sequence",
                    message=f"Duplicate delivery_sequence {seq} in innings {inn_no}",
                    entity_type="delivery",
                    entity_id=did,
                    match_id=match_id,
                )
            )
        seen_seq.add(key)

        if did:
            if did in seen_ids:
                issues.append(
                    issue(
                        code="delivery_duplicate_id",
                        message=f"Duplicate delivery_id {did}",
                        entity_type="delivery",
                        entity_id=did,
                        match_id=match_id,
                    )
                )
            seen_ids.add(did)

        batter = int(d.get("batter_runs") or 0)
        extra = int(d.get("extra_runs") or 0)
        total = int(d.get("total_runs") or 0)
        if batter < 0 or extra < 0 or total < 0:
            issues.append(
                issue(
                    code="delivery_negative_runs",
                    message="Negative runs on delivery",
                    entity_type="delivery",
                    entity_id=did,
                    match_id=match_id,
                )
            )
        if total != batter + extra:
            issues.append(
                issue(
                    code="delivery_runs_inconsistent",
                    message=f"total_runs={total} != batter_runs({batter})+extra_runs({extra})",
                    severity="warning",
                    entity_type="delivery",
                    entity_id=did,
                    match_id=match_id,
                )
            )
        if d.get("warnings"):
            for w in d["warnings"]:
                issues.append(
                    issue(
                        code=f"delivery_clean_{w}",
                        message=f"Cleaner warning on delivery: {w}",
                        severity="warning",
                        entity_type="delivery",
                        entity_id=did,
                        match_id=match_id,
                    )
                )

        runs_by_inn[int(inn_no)] += total
        if d.get("is_wicket"):
            wkts_by_inn[int(inn_no)] += 1

    if bbb_status == "complete" and deliveries:
        for inn in bundle.get("innings") or []:
            inn_no = inn.get("innings_number")
            if inn_no is None or inn.get("total_runs") is None:
                continue
            inn_no = int(inn_no)
            bbb_sum = runs_by_inn.get(inn_no, 0)
            actual = int(inn["total_runs"])
            if bbb_sum != actual:
                issues.append(
                    issue(
                        code="delivery_innings_runs_mismatch",
                        message=(
                            f"Innings {inn_no}: BBB run sum {bbb_sum} != innings total_runs {actual}"
                        ),
                        entity_type="delivery",
                        entity_id=inn.get("innings_id"),
                        match_id=match_id,
                        details={"bbb_sum": bbb_sum, "innings_total": actual},
                    )
                )
            if inn.get("wickets") is not None and wkts_by_inn.get(inn_no, 0) != int(inn["wickets"]):
                issues.append(
                    issue(
                        code="delivery_innings_wickets_mismatch",
                        message=(
                            f"Innings {inn_no}: BBB wickets {wkts_by_inn.get(inn_no, 0)} "
                            f"!= innings wickets {inn['wickets']}"
                        ),
                        severity="warning",
                        entity_type="delivery",
                        entity_id=inn.get("innings_id"),
                        match_id=match_id,
                    )
                )

    declared = bundle.get("delivery_count")
    if declared is not None and deliveries and int(declared) != len(deliveries):
        issues.append(
            issue(
                code="delivery_count_mismatch",
                message=f"delivery_count={declared} but loaded {len(deliveries)} rows",
                severity="warning",
                entity_type="delivery",
                match_id=match_id,
            )
        )

    return issues
