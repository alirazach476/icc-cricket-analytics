# ruff: noqa: E402, E501
"""Build the default view of every dashboard page once and store it compressed in server/precomputed/.

A serverless deployment forgets everything between visits, so without this the first visit to each page waits
1-3 seconds for the analytics to run. With it, a page opened with no filter changed is returned straight from a file;
a page whose filters were changed still computes live (and is cached while the instance stays warm).

    python scripts/precompute_pages.py            # all competitions, editions and pages
    python scripts/precompute_pages.py --check    # list what is missing or older than the databases
    python scripts/precompute_pages.py --only players   # rebuild just some pages after changing them

The file name is ``<competition>__<page>__<edition id or all>.json.gz``; the content is exactly what /api/page returns.
"""

from __future__ import annotations

import argparse
import gzip
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import api, runner


def jobs() -> list[tuple[str, str, dict | None]]:
    """(competition, page, edition dict or None) for every default view the dashboard can open."""
    api.meta()  # builds the editions list (and the Plotly template)
    assert api._META is not None
    out: list[tuple[str, str, dict | None]] = []
    for c in api._META["competitions"]:
        if c.get("hidden"):
            continue
        for p in c["pages"]:
            out.append((c["code"], p, None))  # "All editions"
        for e in c["editions"]:
            for p in e.get("pages") or c["pages"]:
                out.append((e["competition"], p, e))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", help="comma-separated page slugs to rebuild, e.g. players,teams")
    args = ap.parse_args()
    runner.USE_PRECOMPUTED = False  # always compute from the data here
    runner.PRECOMPUTED.mkdir(parents=True, exist_ok=True)
    todo = jobs()
    if args.only:
        wanted = set(args.only.split(","))
        todo = [j for j in todo if j[1] in wanted]
    newest_db = max(f.stat().st_mtime for f in (ROOT / "data" / "warehouse").glob("cricket_gold*.duckdb"))
    started, total, errors = time.time(), 0, []
    for i, (comp, page, ed) in enumerate(todo, 1):
        name = runner.precomputed_name(comp, page, (ed or {}).get("id"))
        f = runner.PRECOMPUTED / name
        if args.check:
            if not f.exists() or f.stat().st_mtime < newest_db:
                print("missing/stale:", name)
            continue
        payload = runner.run_page(page, {}, ed, comp)
        if b'"kind": "error"' in payload:
            errors.append(name)
        f.write_bytes(gzip.compress(payload, 6))
        total += f.stat().st_size
        if i % 25 == 0 or i == len(todo):
            print(f"{i}/{len(todo)} pages  {total / 1e6:.1f} MB  {time.time() - started:.0f}s", flush=True)
    if not args.check:
        print(f"wrote {len(todo)} files to {runner.PRECOMPUTED.relative_to(ROOT)} ({total / 1e6:.1f} MB)")
        if errors:
            print("pages that contain an error alert (check them):", *errors, sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
