# ruff: noqa: E501
"""FastAPI backend for the React dashboard.

Run:  python -m uvicorn server.api:app --port 8000
"""

from __future__ import annotations

import re
from pathlib import Path

from app.utils.flags import flag_map
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from server import editions as E
from server import runner

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"

app = FastAPI(title="CricketWorldCup Analytics API")


def _editions_wc27() -> list[dict]:
    """The 2027 World Cup is a single upcoming edition (no results yet)."""
    from app.utils import database
    from app.utils.database import run

    database.set_competition("wc27")
    s = run("select min(date) a, max(date) b, count(*) n from gold.schedule").iloc[0]
    t = run("select count(*) n, sum(cast(confirmed as int)) c from gold.teams").iloc[0]
    v = run("select count(*) n from gold.venues").iloc[0]
    database.set_competition("wc")
    eid = "wc27-2027"
    a, b = str(s["a"])[:10], str(s["b"])[:10]
    return [
        {
            "id": eid,
            "competition": "wc27",
            "tab": "wc",
            "pages": runner.COMPETITION_PAGES["wc27"],
            "name": "ICC Men's Cricket World Cup 2027",
            "format": "ODI",
            "year": 2027,
            "label": "2027",
            "host": "South Africa; Zimbabwe; Namibia",
            "winner": None,
            "runner_up": None,
            "matches": int(s["n"]),
            "runs_per_match": None,
            "sixes": None,
            "player_of_tournament": None,
            "start": a,
            "end": b,
            "logo": E.logo_for(eid),
            "banner": E.banner_for(eid),
            "theme": E.theme_for(eid),
            "upcoming": True,
            "stats": [
                ["Starts", "2 Oct 2027"],
                ["Final", "21 Nov 2027"],
                ["Teams", f"14 ({int(t['c'])} confirmed)"],
                ["Matches", str(int(s["n"]))],
                ["Venues", str(int(v["n"]))],
                ["Host nations", "3"],
            ],
        }
    ]


def _editions(code: str) -> list[dict]:
    if code == "wc27":
        return _editions_wc27()
    from app.utils import database
    from app.utils.database import run

    database.set_competition(code)
    t = run(
        "select t.tournament_id, t.tournament_name, t.format, t.year, t.host_country, t.winner, t.runner_up, "
        "t.matches, t.runs_per_match, t.sixes, t.player_of_tournament, "
        "cast(min(m.match_date) as varchar) start_date, cast(max(m.match_date) as varchar) end_date "
        "from gold.mart_tournament_summary t left join gold.fact_matches m using(tournament_id) "
        "group by all order by t.year, t.format"
    )
    out = []
    for r in t.to_dict("records"):
        eid = E.edition_id(r["format"], r["year"]) if code == "wc" else f"{code}-{int(r['year'])}"
        out.append(
            {
                "id": eid,
                "competition": code,
                "name": r["tournament_name"],
                "format": r["format"],
                "year": int(r["year"]),
                "label": (re.search(r"\d{4}-\d{2}", r["tournament_name"]) or [str(int(r["year"]))])[
                    0
                ]
                if code == "wtc"
                else str(int(r["year"])),
                "host": r["host_country"],
                "winner": r["winner"],
                "runner_up": r["runner_up"],
                "matches": int(r["matches"]),
                "runs_per_match": None
                if r["runs_per_match"] != r["runs_per_match"]
                else float(r["runs_per_match"]),
                "sixes": None if r["sixes"] != r["sixes"] else int(r["sixes"]),
                "player_of_tournament": r["player_of_tournament"],
                "start": (r["start_date"] or "0000-00-00")[:10],
                "end": (r["end_date"] or "9999-99-99")[:10],
                "logo": E.logo_for(eid),
                "banner": E.banner_for(eid),
                "theme": E.theme_for(eid),
            }
        )
    database.set_competition("wc")
    return out


_META: dict | None = None


def _db_exists(code: str) -> bool:
    from app.utils.database import DB_PATHS

    return DB_PATHS[code].exists()


@app.get("/api/meta")
def meta() -> JSONResponse:
    global _META
    if _META is None:
        from app.utils import theme

        theme.register_plotly()
        import plotly.io as pio

        tpl = pio.templates["cwc"].to_plotly_json()
        comps = [
                {
                    "code": code,
                    "name": E.COMPETITIONS[code]["name"],
                    "long": E.COMPETITIONS[code]["long"],
                    "kicker": E.COMPETITIONS[code]["kicker"],
                    "note": E.COMPETITIONS[code].get("note"),
                    "pages": runner.COMPETITION_PAGES[code],
                    "editions": _editions(code),
                }
                for code in ("wc", "wc27", "ct", "wtc")
                if _db_exists(code)
        ]
        # the upcoming 2027 World Cup is an edition of the World Cups (ODI rail), not a separate tab
        by = {c["code"]: c for c in comps}
        if "wc27" in by and "wc" in by:
            by["wc"]["editions"] += by["wc27"]["editions"]
            by["wc27"]["editions"] = []
            by["wc27"]["hidden"] = True
        _META = {
            "competitions": comps,
            "pages": [{"slug": s, "title": t, "icon": i} for s, t, _, i in runner.PAGES],
            "default_theme": E.DEFAULT_THEME,
            "base_slots": E.BASE_SLOTS,
            "template": tpl,
            "flags": flag_map(),
        }
    return JSONResponse(_META, headers={"Cache-Control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400"})


@app.post("/api/page/{slug}")
async def page(slug: str, request: Request) -> Response:
    body = await request.json()
    edition = None
    competition = body.get("competition") or "wc"
    if body.get("edition"):
        edition = next((e for e in meta_editions() if e["id"] == body["edition"]), None)
        if edition:
            competition = edition["competition"]
    try:
        payload = runner.run_page(slug, body.get("state") or {}, edition, competition)
    except KeyError as exc:
        raise HTTPException(404, f"unknown page {slug}") from exc
    return Response(payload, media_type="application/json")


_MATCH_CACHE: dict[tuple[str, str], bytes] = {}
_CHART_GROUPS = [
    ("Progression", ["Worm", "Run rate"]),
    ("Overs and wickets", ["Over by over", "Wickets timeline"]),
    ("Innings and chase", ["Innings comparison", "Chase"]),
    ("Partnerships and wickets", ["Partnerships", "Fall of wickets"]),
    ("Bowling", ["Dot balls", "Maidens"]),
]


@app.get("/api/match/{match_id}")
def match(match_id: str, competition: str = "wc") -> Response:
    """Everything the match view needs in one call: scoreboard data, charts, branding and the neighbouring matches."""
    import json

    from app.utils import database, match_centre
    from server import stshim

    if competition not in ("wc", "ct", "wtc"):
        raise HTTPException(404, "unknown competition")
    key = (competition, match_id)
    if key in _MATCH_CACHE:
        return Response(_MATCH_CACHE[key], media_type="application/json", headers=_MATCH_HEADERS)
    database.set_competition(competition)
    pl = match_centre.payload(match_id)
    if pl is None:
        raise HTTPException(404, "match not found")
    figs = match_centre.charts(match_id, pl) if pl["has_ball_by_ball"] else {}
    groups = []
    for g, names in _CHART_GROUPS:
        items = [{"name": n, "fig": stshim.figure_to_json(figs[n])} for n in names if n in figs]
        if items:
            groups.append({"group": g, "figs": items})
    body = {"payload": pl, "charts": groups, "neighbours": match_centre.neighbours(match_id, pl["tournament_id"])}
    out = json.dumps(body, allow_nan=False, default=str).encode("utf-8")
    if len(_MATCH_CACHE) > 300:
        _MATCH_CACHE.pop(next(iter(_MATCH_CACHE)))
    _MATCH_CACHE[key] = out
    return Response(out, media_type="application/json", headers=_MATCH_HEADERS)


_MATCH_HEADERS = {"Cache-Control": "public, max-age=300, s-maxage=86400, stale-while-revalidate=86400"}


def meta_editions() -> list[dict]:
    meta()
    assert _META is not None
    return [e for c in _META["competitions"] for e in c["editions"]]


def _warm() -> None:
    """Pre-run every page once so the first click is fast (st.cache_data is filled)."""
    for slug in runner.COMPETITION_PAGES["wc"]:
        try:
            runner.run_page(slug, {}, None)
        except Exception:  # noqa: BLE001 - warm-up is best effort
            pass


@app.on_event("startup")
def _startup() -> None:
    import os
    import threading

    if os.environ.get("VERCEL"):  # serverless: no background warm-up
        return
    threading.Thread(target=_warm, daemon=True).start()


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
