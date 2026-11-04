"""Orchestrate Stage 9 validation over normalized match bundles."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.collectors.scorecard_collector import load_match_manifest
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger
from src.validation.coverage_validation import (
    coverage_snapshot,
    validate_coverage,
    write_coverage_snapshot,
)
from src.validation.delivery_validation import validate_deliveries
from src.validation.innings_validation import validate_innings
from src.validation.issues import summarize_issues
from src.validation.match_validation import validate_match
from src.validation.player_validation import validate_players

logger = get_logger(__name__)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON %s: %s", path, exc)
        return None


def validate_match_bundle(bundle: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    root = root or get_project_root()
    match_id = bundle.get("match_id") or (bundle.get("match") or {}).get("match_id")
    deliveries_doc = None
    if match_id:
        deliveries_doc = _load_json(root / "data" / "processed" / "deliveries" / f"{match_id}.json")

    issues: list[dict[str, Any]] = []
    issues.extend(validate_match(bundle))
    issues.extend(validate_innings(bundle))
    issues.extend(validate_players(bundle))
    issues.extend(validate_deliveries(bundle, deliveries_doc=deliveries_doc))

    summary = summarize_issues(issues)
    return {
        "match_id": match_id,
        "tournament_id": bundle.get("tournament_id") or (bundle.get("match") or {}).get("tournament_id"),
        "ok": summary["error"] == 0,
        "issue_summary": summary,
        "issues": issues,
    }


def validate_dataset(
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
    limit: int | None = None,
    include_coverage: bool = True,
) -> dict[str, Any]:
    root = get_project_root()
    rows = load_match_manifest()
    if tournament_id:
        rows = [r for r in rows if r.get("tournament_id") == tournament_id]
    if match_ids:
        wanted = set(match_ids)
        rows = [r for r in rows if r.get("match_id") in wanted]

    # Prefer normalized artifacts
    candidates: list[str] = []
    for row in rows:
        mid = row.get("match_id") or ""
        if (root / "data" / "processed" / "matches" / f"{mid}.json").exists():
            candidates.append(mid)
        elif match_ids:
            candidates.append(mid)
    if not match_ids and not tournament_id:
        # If no filter, validate all processed match files
        candidates = sorted(p.stem for p in (root / "data" / "processed" / "matches").glob("*.json"))

    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for mid in candidates:
        if mid not in seen:
            seen.add(mid)
            ordered.append(mid)
    if limit is not None:
        ordered = ordered[: max(0, limit)]

    started = utc_now_iso()
    match_results: list[dict[str, Any]] = []
    all_issues: list[dict[str, Any]] = []

    for mid in ordered:
        path = root / "data" / "processed" / "matches" / f"{mid}.json"
        bundle = _load_json(path)
        if not bundle:
            result = {
                "match_id": mid,
                "ok": False,
                "issue_summary": {"total": 1, "error": 1, "warning": 0, "info": 0},
                "issues": [
                    {
                        "code": "normalized_missing",
                        "message": f"Missing processed match file: {path}",
                        "severity": "error",
                        "entity_type": "match",
                        "entity_id": mid,
                        "match_id": mid,
                        "details": {},
                    }
                ],
            }
        else:
            result = validate_match_bundle(bundle, root=root)
        match_results.append(result)
        all_issues.extend(result.get("issues") or [])

    coverage_issues: list[dict[str, Any]] = []
    coverage: dict[str, Any] | None = None
    if include_coverage:
        coverage = coverage_snapshot(tournament_id)
        coverage_issues = validate_coverage(tournament_id)
        all_issues.extend(coverage_issues)
        write_coverage_snapshot(tournament_id)

    summary = summarize_issues(all_issues)
    matches_ok = sum(1 for r in match_results if r.get("ok"))
    matches_failed = len(match_results) - matches_ok

    report = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "tournament_id": tournament_id,
        "matches_validated": len(match_results),
        "matches_ok": matches_ok,
        "matches_failed": matches_failed,
        "issue_summary": summary,
        "coverage": coverage,
        "coverage_issues": coverage_issues,
        "match_results": match_results,
        "claims_complete_coverage": False,
    }

    out_dir = ensure_dir(root / "data" / "processed" / "validation")
    suffix = tournament_id or "all"
    report_path = out_dir / f"validation_report_{suffix}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)

    # Flat issues CSV for triage
    csv_path = out_dir / f"validation_issues_{suffix}.csv"
    fieldnames = [
        "severity",
        "code",
        "entity_type",
        "entity_id",
        "match_id",
        "message",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in all_issues:
            writer.writerow(row)
    report["issues_csv_path"] = str(csv_path)
    return report
