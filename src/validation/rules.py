"""Declarative data-quality rule engine (Stage 3).

A ``Rule`` describes one check as "bad rows over total rows" grouped by tournament. The engine
turns it into SQL, so each rule stays small and readable and every result is a pass rate that can
be scored and traced back to example rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Dimension = Literal[
    "completeness",
    "uniqueness",
    "validity",
    "referential_integrity",
    "consistency",
    "historical_coverage",
]
Severity = Literal["critical", "major", "minor"]

DIMENSIONS: tuple[str, ...] = (
    "completeness",
    "uniqueness",
    "validity",
    "referential_integrity",
    "consistency",
    "historical_coverage",
)
# A critical defect (breaks joins or totals) counts three times a minor one (cosmetic / optional).
SEVERITY_WEIGHT: dict[str, int] = {"critical": 3, "major": 2, "minor": 1}
GLOBAL = "(global)"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    dataset: str
    dimension: Dimension
    severity: Severity
    description: str
    from_: str = ""
    bad: str = ""
    where: str | None = None
    tid: str = "m.tournament_id"
    key: str | None = None
    sql: str | None = None  # raw override returning (tournament_id, total, failed)
    note: str = field(default="")  # known limitation / why this can be a false positive

    def count_sql(self) -> str:
        if self.sql:
            return self.sql
        where = f"where {self.where}" if self.where else ""
        return (
            f"select {self.tid} as tournament_id, count(*) as total, "
            f"count(*) filter (where {self.bad}) as failed "
            f"from {self.from_} {where} group by 1"
        )

    def example_sql(self, limit: int = 5) -> str | None:
        if self.sql or not self.key:
            return None
        cond = f"({self.bad})" + (f" and ({self.where})" if self.where else "")
        return f"select {self.key} from {self.from_} where {cond} limit {limit}"


def validate_rule_ids(rules: list[Rule]) -> None:
    """Rule ids must be unique and dimensions/severities known (fails fast at import/test time)."""
    seen: set[str] = set()
    for r in rules:
        if r.rule_id in seen:
            raise ValueError(f"duplicate rule id: {r.rule_id}")
        seen.add(r.rule_id)
        if r.dimension not in DIMENSIONS:
            raise ValueError(f"{r.rule_id}: unknown dimension {r.dimension}")
        if r.severity not in SEVERITY_WEIGHT:
            raise ValueError(f"{r.rule_id}: unknown severity {r.severity}")
        if not r.sql and not (r.from_ and r.bad):
            raise ValueError(f"{r.rule_id}: needs from_/bad or sql")
