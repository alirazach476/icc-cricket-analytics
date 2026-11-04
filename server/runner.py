# ruff: noqa: E501
"""Run a Streamlit page script under the shim and return its UI tree."""

from __future__ import annotations

import runpy
import sys
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import stshim  # noqa: E402

stshim.install()  # must happen before any app module imports ``streamlit``

import json  # noqa: E402

from app.utils import database, theme  # noqa: E402

PAGES = [
    ("home", "Home", "app/dashboard.py", "home"),
    ("tournaments", "Tournaments", "app/pages/01_Tournament_Explorer.py", "trophy"),
    ("players", "Players", "app/pages/02_Player_Analytics.py", "user"),
    ("teams", "Teams", "app/pages/03_Team_Analytics.py", "shield"),
    ("squads", "Squads", "app/pages/04_Squads.py", "users"),
    ("matches", "Matches", "app/pages/05_Match_Analytics.py", "swords"),
    ("ball-by-ball", "Ball by Ball", "app/pages/06_Ball_by_Ball_Analytics.py", "target"),
    ("research", "Statistics", "app/pages/07_Statistical_Research.py", "flask"),
    ("ml", "Machine Learning", "app/pages/08_Machine_Learning.py", "brain"),
    ("data", "Data Engineering", "app/pages/09_Data_Engineering.py", "database"),
    ("records", "Records", "app/pages/10_Historical_Records.py", "scroll"),
    ("insights", "Statistics", "app/competition_pages/competition_statistics.py", "flask"),
]
_BY_SLUG = {p[0]: p for p in PAGES}

LOCK = threading.Lock()
_CACHE: OrderedDict[str, bytes] = OrderedDict()
_CACHE_MAX = 80


def _hero(title: str, subtitle: str, chips: list[str] | None = None) -> None:
    stshim.CTX.hero = {"title": title, "subtitle": subtitle, "chips": chips or []}


# the pages draw their own banner through these helpers; the React shell draws it instead
theme.hero = _hero  # type: ignore[assignment]
theme.inject = theme.register_plotly  # type: ignore[assignment]


# pages that make sense for each competition (the ML and statistics pages are trained on World Cup data)
# the 2027 World Cup has not been played: its home page is the schedule / venues / teams preview
PAGE_OVERRIDES = {("wc27", "home"): "app/competition_pages/world_cup_2027.py"}

COMPETITION_PAGES = {
    "wc27": ["home"],
    "wc": [p[0] for p in PAGES if p[0] != "insights"],
    "ct": [
        "home",
        "tournaments",
        "players",
        "teams",
        "squads",
        "matches",
        "ball-by-ball",
        "insights",
        "records",
    ],
    "wtc": [
        "home",
        "tournaments",
        "players",
        "teams",
        "squads",
        "matches",
        "ball-by-ball",
        "insights",
        "records",
    ],
}


def run_page(slug: str, state: dict | None, edition: dict | None, competition: str = "wc") -> bytes:
    """Return the JSON-encoded UI tree for a page (cached per widget state + edition)."""
    if slug not in _BY_SLUG:
        raise KeyError(slug)
    key = json.dumps([competition, slug, state or {}, edition or {}], sort_keys=True, default=str)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    path = ROOT / PAGE_OVERRIDES.get((competition, slug), _BY_SLUG[slug][2])
    started = time.perf_counter()
    with LOCK:
        ctx = stshim.Ctx(state or {}, edition, competition)
        stshim.CTX = ctx
        database.set_competition(competition)
        error: str | None = None
        try:
            runpy.run_path(str(path), run_name="__main__")
        except stshim.StopRun:
            pass
        except Exception:  # noqa: BLE001 - shown to the user instead of a blank page
            error = traceback.format_exc()
        if error:
            ctx.body.nodes.append(
                {
                    "t": "alert",
                    "kind": "error",
                    "text": f"This page raised an error:\n\n{error[-1800:]}",
                }
            )
        out = {
            "slug": slug,
            "competition": competition,
            "hero": ctx.hero,
            "sidebar": ctx.sidebar.nodes,
            "body": ctx.body.nodes,
            "ms": int((time.perf_counter() - started) * 1000),
            "unsupported": sorted(ctx.unsupported),
            "notes": ctx.notes,
        }
        payload = json.dumps(out, allow_nan=False, default=str).encode("utf-8")
    _CACHE[key] = payload
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return payload
