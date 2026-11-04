"""Start the React dashboard (FastAPI backend + built front end) on http://localhost:8000.

python scripts/run_react_dashboard.py            # serve web/dist
python scripts/run_react_dashboard.py --build    # build the front end first (Node 18+)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def build() -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("Node.js/npm not found. Install Node 18+ to build the front end.")
    if not (WEB / "node_modules").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=WEB, check=True)
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="build the React app first")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if a.build or not (WEB / "dist" / "index.html").exists():
        build()
    import uvicorn

    if not a.no_browser:
        webbrowser.open(f"http://localhost:{a.port}")
    uvicorn.run("server.api:app", host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
