"""Load processed standings and squads into the configured database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.connection import session_scope  # noqa: E402
from src.database.load_standings_squads import load_standings_and_squads  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", help="Limit to one tournament_id")
    args = parser.parse_args()
    with session_scope() as session:
        report = load_standings_and_squads(session, tournament_id=args.tournament)
    print(json.dumps(report, indent=2))
    return 1 if any("error" in v for v in report.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
