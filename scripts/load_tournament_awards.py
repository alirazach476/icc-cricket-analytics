"""Load config/tournament_awards.csv into the tournament_awards table (idempotent)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.connection import session_scope  # noqa: E402
from src.database.load_awards import load_awards, read_awards  # noqa: E402


def main() -> int:
    with session_scope() as session:
        report = load_awards(session, read_awards())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
