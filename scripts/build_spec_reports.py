# ruff: noqa: E501
"""Build the six reports named in the brief (each with the ten required sections) and their figures."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.reporting.spec_reports import write_all  # noqa: E402


def main() -> int:
    for p in write_all():
        print("report:", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
