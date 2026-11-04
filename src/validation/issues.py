"""Shared validation issue model (Stage 9)."""

from __future__ import annotations

from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


def issue(
    *,
    code: str,
    message: str,
    severity: Severity = "error",
    entity_type: str,
    entity_id: str | None = None,
    match_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "match_id": match_id,
        "details": details or {},
    }


def summarize_issues(issues: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": len(issues), "error": 0, "warning": 0, "info": 0}
    for row in issues:
        sev = row.get("severity") or "error"
        if sev in summary:
            summary[sev] += 1
    return summary
