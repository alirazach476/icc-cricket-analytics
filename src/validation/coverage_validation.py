"""Tournament / dataset coverage checks (Stage 9).

Never claims complete coverage — reports observed counts and gaps only.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.utils.config import get_project_root
from src.validation.issues import issue


def _manifest_rows(tournament_id: str | None = None) -> list[dict[str, str]]:
    root = get_project_root()
    path = root / "data" / "manifests" / "match_urls.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if tournament_id:
        rows = [r for r in rows if r.get("tournament_id") == tournament_id]
    return rows


def coverage_snapshot(tournament_id: str | None = None) -> dict[str, Any]:
    """Count discovered / collected / normalized / BBB statuses without fabricating."""
    root = get_project_root()
    rows = _manifest_rows(tournament_id)
    discovered = len(rows)

    scorecards = 0
    normalized = 0
    bbb_counts = {"complete": 0, "partial": 0, "unavailable": 0, "not_checked": 0, "other": 0}
    cancelled = 0
    missing_scorecard: list[str] = []
    missing_normalized: list[str] = []

    for row in rows:
        mid = row.get("match_id") or ""
        if str(row.get("is_cancelled", "")).lower() in {"true", "1"}:
            cancelled += 1
        sc_path = root / "data" / "raw" / "scorecards" / mid / "scorecard.json"
        if sc_path.exists():
            scorecards += 1
        else:
            missing_scorecard.append(mid)

        norm_path = root / "data" / "processed" / "matches" / f"{mid}.json"
        if norm_path.exists():
            normalized += 1
            try:
                import json

                bundle = json.loads(norm_path.read_text(encoding="utf-8"))
                status = bundle.get("ball_by_ball_status") or "not_checked"
            except Exception:  # noqa: BLE001
                status = "other"
            if status in bbb_counts:
                bbb_counts[status] += 1
            else:
                bbb_counts["other"] += 1
        else:
            missing_normalized.append(mid)
            # Fall back to manifest column if present
            status = row.get("ball_by_ball_status") or "not_checked"
            if status in bbb_counts:
                bbb_counts[status] += 1
            else:
                bbb_counts["other"] += 1

    return {
        "tournament_id": tournament_id,
        "discovered_matches": discovered,
        "cancelled_matches": cancelled,
        "scorecards_collected": scorecards,
        "normalized_matches": normalized,
        "ball_by_ball": bbb_counts,
        "scorecard_coverage_pct": round(100.0 * scorecards / discovered, 2) if discovered else 0.0,
        "normalized_coverage_pct": round(100.0 * normalized / discovered, 2) if discovered else 0.0,
        "bbb_complete_pct": round(100.0 * bbb_counts["complete"] / discovered, 2) if discovered else 0.0,
        "missing_scorecard_match_ids": missing_scorecard,
        "missing_normalized_match_ids": missing_normalized,
        "claims_complete_coverage": False,
        "notes": (
            "Coverage percentages reflect collected/normalized artifacts only. "
            "Do not treat this snapshot as a claim of complete historical coverage."
        ),
    }


def validate_coverage(tournament_id: str | None = None) -> list[dict[str, Any]]:
    snap = coverage_snapshot(tournament_id)
    issues: list[dict[str, Any]] = []
    discovered = snap["discovered_matches"]

    if discovered == 0:
        issues.append(
            issue(
                code="coverage_no_matches",
                message="No matches in manifest for coverage scope",
                severity="warning",
                entity_type="coverage",
                entity_id=tournament_id,
            )
        )
        return issues

    if snap["scorecards_collected"] < discovered:
        issues.append(
            issue(
                code="coverage_scorecard_gaps",
                message=(
                    f"Scorecards collected for {snap['scorecards_collected']}/{discovered} "
                    "discovered matches"
                ),
                severity="info",
                entity_type="coverage",
                entity_id=tournament_id,
                details={"missing_count": len(snap["missing_scorecard_match_ids"])},
            )
        )

    if snap["normalized_matches"] < snap["scorecards_collected"]:
        issues.append(
            issue(
                code="coverage_normalize_gaps",
                message=(
                    f"Normalized {snap['normalized_matches']}/{snap['scorecards_collected']} "
                    "collected scorecards"
                ),
                severity="warning",
                entity_type="coverage",
                entity_id=tournament_id,
                details={"missing_count": len(snap["missing_normalized_match_ids"])},
            )
        )

    bbb = snap["ball_by_ball"]
    if bbb["unavailable"] or bbb["partial"] or bbb["not_checked"]:
        issues.append(
            issue(
                code="coverage_bbb_incomplete",
                message=(
                    "Ball-by-ball not complete for all matches: "
                    f"complete={bbb['complete']}, partial={bbb['partial']}, "
                    f"unavailable={bbb['unavailable']}, not_checked={bbb['not_checked']}"
                ),
                severity="info",
                entity_type="coverage",
                entity_id=tournament_id,
                details=bbb,
            )
        )

    return issues


def write_coverage_snapshot(tournament_id: str | None, path: Path | None = None) -> Path:
    import json

    from src.utils.helpers import ensure_dir, utc_now_iso

    root = get_project_root()
    out = path or (ensure_dir(root / "data" / "processed" / "validation") / (
        f"coverage_{tournament_id or 'all'}.json"
    ))
    snap = coverage_snapshot(tournament_id)
    snap["generated_at"] = utc_now_iso()
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
