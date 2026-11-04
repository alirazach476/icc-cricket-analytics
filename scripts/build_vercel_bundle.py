# ruff: noqa: E501
"""Stage a deployable copy of the React dashboard for Vercel (FastAPI function + static React build).

    cd web && npm install && npx vite build && cd ..
    python scripts/build_vercel_bundle.py build/vercel
    cd build/vercel && vercel link --yes --project <name> && vercel deploy --prod --yes

What it does
------------
* copies only what the dashboard reads (code, config, reports, small feature files),
* compacts the four gold DuckDB files (about half the size, identical rows) so the function stays under
  Vercel's 500 MB limit,
* ships the pre-built default view of every page (``scripts/precompute_pages.py``; delete
  ``server/precomputed`` to rebuild after the data changes),
* writes ``index.py`` (the FastAPI app), a pinned ``requirements.txt`` / minimal ``pyproject.toml`` and ``vercel.json``,
* serves the React build from ``public/`` (CDN) and the API from the function.

The DuckDB file format is version specific, so ``duckdb`` is pinned to the version installed here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build" / "vercel").resolve()
DBS = ["cricket_gold.duckdb", "cricket_gold_ct.duckdb", "cricket_gold_wtc.duckdb", "cricket_gold_wc27.duckdb"]
# libraries the pages import at run time (pinned to the versions the project was built with)
PINNED = ["fastapi", "pandas", "numpy", "duckdb", "plotly", "scipy", "scikit-learn", "joblib", "sqlalchemy", "statsmodels", "PyYAML", "pydantic", "pydantic-settings"]


def compact(src: Path, dst: Path) -> None:
    stem = src.name[: -len(".duckdb")]
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{src.as_posix()}' AS o (READ_ONLY)")
    con.execute(f"ATTACH '{dst.as_posix()}' AS {stem}")
    con.execute(f"COPY FROM DATABASE o TO {stem}")
    con.close()


def main() -> None:
    pre = ROOT / "server" / "precomputed"
    if not pre.exists() or not any(pre.iterdir()):
        # default view of every page, built once so the first visit does not wait for the analytics to run
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "precompute_pages.py")])
    if not (ROOT / "web" / "dist").exists():
        sys.exit("Build the React app first: cd web && npm install && npx vite build")
    if OUT.exists():
        for p in OUT.iterdir():
            if p.name != ".vercel":  # keep the project link between runs
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    for d in ["app", "server", "src", "config", "sql", "models", "reports"]:
        shutil.copytree(ROOT / d, OUT / d, ignore=ign)
    for d in ["features", "manifests", "silver", "gold", "synthetic"]:
        if (ROOT / "data" / d).exists():
            shutil.copytree(ROOT / "data" / d, OUT / "data" / d, ignore=ign)
    manifest = ROOT / "data" / "bronze" / "_manifest.json"
    if manifest.exists():
        (OUT / "data" / "bronze").mkdir(parents=True, exist_ok=True)
        shutil.copy(manifest, OUT / "data" / "bronze" / "_manifest.json")
    (OUT / "data" / "warehouse").mkdir(parents=True, exist_ok=True)
    for n in DBS:
        compact(ROOT / "data" / "warehouse" / n, OUT / "data" / "warehouse" / n)
    shutil.copytree(ROOT / "web" / "dist", OUT / "public")
    # serverless bundles drop public/ folders, so ship the list of logo files the API links to
    (OUT / "server" / "logo_files.json").write_text(
        json.dumps(sorted(f.name for f in (ROOT / "web" / "public" / "logos").glob("*.png")))
    )
    (OUT / "index.py").write_text(
        "import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from server.api import app  # noqa: E402,F401\n",
        encoding="utf-8",
    )
    reqs = [f"{p}=={metadata.version(p)}" for p in PINNED] + ["xgboost-cpu==" + metadata.version("xgboost"), "tenacity>=8", "python-dotenv>=1"]
    (OUT / "requirements.txt").write_text("\n".join(reqs) + "\n", encoding="utf-8")
    nl = chr(10)
    (OUT / "pyproject.toml").write_text(
        nl.join(['[project]', 'name = "icc-cricket-analytics"', 'version = "1.0.0"', 'requires-python = ">=3.12"', "dependencies = ["] + [f'  "{r}",' for r in reqs] + ["]", ""]),
        encoding="utf-8",
    )
    (OUT / ".python-version").write_text("3.12\n", encoding="utf-8")
    cache = lambda v: [{"key": "Cache-Control", "value": v}]  # noqa: E731
    (OUT / "vercel.json").write_text(
        json.dumps(
            {
                # run the function in Mumbai: the dashboard is used from South Asia (default is Washington)
                "regions": ["bom1"],
                "functions": {"index.py": {"maxDuration": 60, "excludeFiles": "{**/tests/**,**/__pycache__/**,**/*.pyc,**/plotly/package_data/datasets/**}"}},
                "headers": [
                    {"source": "/assets/(.*)", "headers": cache("public, max-age=31536000, immutable")},
                    {"source": "/logos/(.*)", "headers": cache("public, max-age=604800")},
                    {"source": "/flags/(.*)", "headers": cache("public, max-age=604800")},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / ".vercelignore").write_text("__pycache__\n*.pyc\n.env.local\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file() and ".vercel" not in f.parts)
    print(f"staged {OUT} ({size / 1e6:.0f} MB, excluding Python packages)")


if __name__ == "__main__":
    main()
