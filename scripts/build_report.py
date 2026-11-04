"""Stage 16: build reports/executive_report.md from the gold layer and stage reports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.reporting.executive_report import write  # noqa: E402


def main() -> int:
    print(f"report: {write().relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
