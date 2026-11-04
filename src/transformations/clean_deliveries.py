"""Clean ball-by-ball delivery records (Stage 8).

Never invents missing deliveries. Flags inconsistencies without fabricating fixes.
"""

from __future__ import annotations

from typing import Any


def _int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clean_delivery(delivery: dict[str, Any]) -> dict[str, Any] | None:
    if not delivery:
        return None
    match_id = delivery.get("match_id")
    innings_number = delivery.get("innings_number")
    delivery_sequence = delivery.get("delivery_sequence")
    if not match_id or innings_number is None or delivery_sequence is None:
        return None

    batter_runs = _int(delivery.get("batter_runs"))
    extra_runs = _int(delivery.get("extra_runs"))
    total_runs = delivery.get("total_runs")
    if total_runs is None:
        total_runs = batter_runs + extra_runs
    else:
        total_runs = _int(total_runs)

    warnings: list[str] = []
    if total_runs < 0 or batter_runs < 0 or extra_runs < 0:
        warnings.append("negative_runs")
    if total_runs != batter_runs + extra_runs:
        # Keep source totals; note inconsistency rather than overwriting
        warnings.append("runs_inconsistent_with_components")

    is_wide = bool(delivery.get("is_wide"))
    is_legal = delivery.get("is_legal_delivery")
    if is_legal is None:
        is_legal = not is_wide

    delivery_id = delivery.get("delivery_id") or f"{match_id}_{innings_number}_{delivery_sequence}"
    return {
        "delivery_id": delivery_id,
        "match_id": str(match_id),
        "innings_id": delivery.get("innings_id") or f"{match_id}_{innings_number}",
        "innings_number": int(innings_number),
        "innings_type": delivery.get("innings_type") or "standard",
        "over_number": delivery.get("over_number"),
        "ball_number": delivery.get("ball_number"),
        "delivery_sequence": int(delivery_sequence),
        "legal_ball_number": delivery.get("legal_ball_number"),
        "batter_id": delivery.get("batter_id"),
        "non_striker_id": delivery.get("non_striker_id"),
        "bowler_id": delivery.get("bowler_id"),
        "batter_runs": batter_runs,
        "extra_runs": extra_runs,
        "total_runs": total_runs,
        "extras_type": delivery.get("extras_type"),
        "is_wide": is_wide,
        "is_no_ball": bool(delivery.get("is_no_ball")),
        "is_bye": bool(delivery.get("is_bye")),
        "is_leg_bye": bool(delivery.get("is_leg_bye")),
        "is_penalty": bool(delivery.get("is_penalty")),
        "is_wicket": bool(delivery.get("is_wicket")),
        "dismissal_type": delivery.get("dismissal_type"),
        "dismissed_player_id": delivery.get("dismissed_player_id"),
        "fielder_id": delivery.get("fielder_id"),
        "commentary_text": delivery.get("commentary_text"),
        "is_legal_delivery": bool(is_legal),
        "source_name": delivery.get("source_name"),
        "source_url": delivery.get("source_url"),
        "source_ball_id": delivery.get("source_ball_id"),
        "warnings": warnings,
    }


def assign_legal_ball_numbers(deliveries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill legal_ball_number per innings from cleaned deliveries (1-based among legal balls)."""
    counters: dict[int, int] = {}
    out: list[dict[str, Any]] = []
    for raw in deliveries:
        cleaned = clean_delivery(raw)
        if not cleaned:
            continue
        inn = cleaned["innings_number"]
        if cleaned["is_legal_delivery"]:
            counters[inn] = counters.get(inn, 0) + 1
            cleaned["legal_ball_number"] = counters[inn]
        else:
            cleaned["legal_ball_number"] = cleaned.get("legal_ball_number")
        out.append(cleaned)
    return out


def clean_delivery_list(deliveries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not deliveries:
        return []
    cleaned = assign_legal_ball_numbers(deliveries)
    cleaned.sort(key=lambda d: (d["innings_number"], d["delivery_sequence"]))
    return cleaned
