"""Run dbt commands against the local DuckDB warehouse (Stage 12)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = PROJECT_ROOT / "dbt"


def _dbt_executable() -> str:
    candidate = PROJECT_ROOT / ".venv" / "Scripts" / "dbt.exe"
    if candidate.exists():
        return str(candidate)
    unix = PROJECT_ROOT / ".venv" / "bin" / "dbt"
    if unix.exists():
        return str(unix)
    return "dbt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wrapper around dbt for this project.",
        add_help=True,
    )
    parser.add_argument(
        "--target",
        default="dev",
        help="dbt target from profiles.yml (dev | odi_2023)",
    )
    parser.add_argument(
        "--tournament",
        help="Optional tournament_id var filter for models that support it.",
    )
    parser.add_argument(
        "dbt_args",
        nargs=argparse.REMAINDER,
        help="dbt command and args after -- , e.g. run | test | build --select marts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dbt_args = list(args.dbt_args)
    if dbt_args and dbt_args[0] == "--":
        dbt_args = dbt_args[1:]
    if not dbt_args:
        print("Usage: python scripts/run_dbt.py [--target dev] [--tournament ODI_M_2023] -- run")
        print("   or: python scripts/run_dbt.py run")
        # Allow `python scripts/run_dbt.py run` via treating first positional without --
        return 2

    # Support both:
    #   python scripts/run_dbt.py run
    #   python scripts/run_dbt.py -- run --select marts
    cmd = [
        _dbt_executable(),
        *dbt_args,
        "--project-dir",
        str(DBT_DIR),
        "--profiles-dir",
        str(DBT_DIR),
        "--target",
        args.target,
    ]
    if args.tournament:
        cmd.extend(["--vars", f'{{"tournament_id": "{args.tournament}"}}'])

    print("Running:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return int(completed.returncode)


if __name__ == "__main__":
    # Normalize: if first argv after script is a dbt verb, insert implicit remainder
    verbs = {"run", "test", "build", "compile", "docs", "debug", "seed", "clean", "parse", "list", "show"}
    if len(sys.argv) > 1 and sys.argv[1] in verbs:
        sys.argv.insert(1, "--")
    raise SystemExit(main())
