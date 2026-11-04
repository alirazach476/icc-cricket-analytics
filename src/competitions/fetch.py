"""Download the open Cricsheet archives and keep the matches of the extra competitions.

Raw files are kept as published (with a sha256 manifest), like the bronze layer.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "competitions"
URLS = {
    "odis": "https://cricsheet.org/downloads/odis_male_json.zip",
    "tests": "https://cricsheet.org/downloads/tests_male_json.zip",
}
# (archive, event name, competition code)
SELECT = [
    ("odis", "ICC Champions Trophy", "CT"),
    ("tests", "ICC World Test Championship", "WTC"),
]


def _download(name: str, force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    zp = RAW / f"{name}_male_json.zip"
    if force or not zp.exists():
        req = urllib.request.Request(URLS[name], headers={"User-Agent": "cricket-analytics/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(zp, "wb") as f:  # noqa: S310
            f.write(r.read())
    return zp


def _espn_ids(code: str) -> set[str] | None:
    """Match ids of every Test in a World Test Championship cycle (ESPNcricinfo's own series schedule)."""
    dirs = sorted((ROOT / "data" / "competitions" / "espn").glob(f"{code}_M_*"))
    ids: set[str] = set()
    for d in dirs:
        f = d / "schedule.json"
        if f.exists():
            ids |= {
                str(m["match_id"]) for m in json.loads(f.read_text(encoding="utf-8"))["matches"]
            }
    return ids or None


def download(force: bool = False) -> None:
    for name in URLS:
        _download(name, force)


def select(clear: bool = False) -> dict:
    """Copy the matches that belong to the extra competitions out of the archives."""
    manifest: dict = {"fetched_at": datetime.now(UTC).isoformat(), "files": []}
    for archive, event, code in SELECT:
        zp = _download(archive)
        out = RAW / "cricsheet" / code
        out.mkdir(parents=True, exist_ok=True)
        wanted = _espn_ids(code) if code == "WTC" else None
        with zipfile.ZipFile(zp) as z:
            for member in z.namelist():
                if not member.endswith(".json"):
                    continue
                mid = Path(member).stem
                raw = z.read(member)
                info = json.loads(raw)["info"]
                if wanted is not None:
                    if mid not in wanted:
                        continue
                elif (info.get("event") or {}).get("name") != event:
                    continue
                if (
                    code == "WTC"
                    and wanted is None
                    and (info.get("event") or {}).get("stage") != "Final"
                ):
                    continue  # no cycle schedule available yet: fall back to the three tagged finals
                target = out / Path(member).name
                if not target.exists():
                    target.write_bytes(raw)
                manifest["files"].append(
                    {
                        "competition": code,
                        "file": str(target.relative_to(ROOT)).replace("\\", "/"),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "source": URLS[archive],
                        "date": info["dates"][0],
                    }
                )
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def fetch(force: bool = False) -> dict:
    download(force)
    return select()


if __name__ == "__main__":
    m = fetch()
    from collections import Counter

    print(Counter((f["competition"], f["date"][:4]) for f in m["files"]))
