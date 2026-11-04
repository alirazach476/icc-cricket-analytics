"""Load config/manual_squads.csv into the squads table (idempotent)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.connection import session_scope  # noqa: E402
from src.database.load_manual_squads import load_manual_squads, read_manual_squads  # noqa: E402


def main() -> int:
    with session_scope() as session:
        report = load_manual_squads(session, read_manual_squads())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
