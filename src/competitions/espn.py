# ruff: noqa: E501
"""ESPNcricinfo supplement for the Champions Trophy.

Uses the project's own collector (identifying user agent, robots.txt check, throttling, hard stop on
401/403/429) and the existing page parsers. Cricsheet has no abandoned / no-result matches and no 2002
edition, no squad lists and no points tables; ESPNcricinfo has all of them.

Raw HTML is kept under ``data/raw/competitions/espn/<tournament_id>/`` and parsed JSON under
``data/competitions/espn/<tournament_id>/`` (never inside the World Cup folders).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.collectors.base_collector import BaseCollector
from src.competitions.silver_cricsheet import ROOT, load_registry
from src.parsers.match_list_parser import parse_match_schedule_html
from src.parsers.scorecard_parser import parse_scorecard_html
from src.parsers.standings_parser import (
    parse_squad_html,
    parse_squad_index_html,
    parse_standings_html,
)

ORIGIN = "https://www.espncricinfo.com"
RAW = ROOT / "data" / "raw" / "competitions" / "espn"
PARSED = ROOT / "data" / "competitions" / "espn"


def parsed_dir(tid: str) -> Path:
    return PARSED / tid


def _get(collector: BaseCollector, url: str, cache: Path) -> str | None:
    """Fetch a page once and keep the raw HTML next to the project (cached on re-runs)."""
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    res = collector.fetch_html(url)
    if not res.ok or not res.content:
        print(f"  ! {url}: {res.access_status} {res.error}")
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(res.content, encoding="utf-8")
    return res.content


def collect_edition(
    collector: BaseCollector,
    code: str,
    edition: dict[str, Any],
    have_ids: set[str],
    all_scorecards: bool = False,
) -> dict[str, Any]:
    year = edition["year"]
    tid = f"{code}_M_{year}"
    slug = edition["espn_series"]
    base = f"{ORIGIN}/series/{slug}"
    raw, out = RAW / tid, PARSED / tid
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"tournament_id": tid}

    # --- schedule: every match, including abandoned ones
    html = _get(collector, f"{base}/match-schedule-fixtures-and-results", raw / "schedule.html")
    sched = (
        parse_match_schedule_html(html or "", tournament_id=tid, source_url=base)
        if html
        else {"matches": []}
    )
    (out / "schedule.json").write_text(json.dumps(sched, indent=1, default=str), encoding="utf-8")
    matches = sched["matches"]
    report["schedule_matches"] = len(matches)

    # --- points table
    html = _get(collector, f"{base}/points-table-standings", raw / "standings.html")
    if html:
        st = parse_standings_html(
            html, tournament_id=tid, source_url=f"{base}/points-table-standings"
        )
        (out / "standings.json").write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")
        report["standings_rows"] = len(st.get("rows", []))

    # --- squads
    html = _get(collector, f"{base}/squads", raw / "squads_index.html")
    squads = []
    if html:
        for link in parse_squad_index_html(html):
            sq_html = _get(
                collector,
                f"{ORIGIN}{link}",
                raw / "squads" / f"{link.rstrip('/').split('/')[-2]}.html",
            )
            if not sq_html:
                continue
            p = parse_squad_html(sq_html, tournament_id=tid, source_url=f"{ORIGIN}{link}")
            if p["parse_status"] == "ok":
                squads.append(p)
    (out / "squads.json").write_text(
        json.dumps({"tournament_id": tid, "squads": squads}, indent=1, default=str),
        encoding="utf-8",
    )
    report["squads"] = len(squads)
    report["squad_players"] = sum(len(s["players"]) for s in squads)

    # --- scorecards for the matches the ball-by-ball source does not have
    sc_dir = out / "scorecards"
    sc_dir.mkdir(exist_ok=True)
    n_cards = 0
    for m in matches:
        mid = str(m["match_id"])
        if mid in have_ids and not all_scorecards:
            continue
        if m.get("result_type") in ("ABANDONED",) and not m.get("has_scorecard"):
            pass  # still try: an abandoned match may have a (blank) scorecard page
        html = (
            _get(collector, m["scorecard_url"], raw / f"scorecard_{mid}.html")
            if m.get("scorecard_url")
            else None
        )
        if not html:
            continue
        card = parse_scorecard_html(
            html, match_id=mid, tournament_id=tid, source_url=m["scorecard_url"]
        )
        (sc_dir / f"{mid}.json").write_text(
            json.dumps(card, indent=1, default=str), encoding="utf-8"
        )
        n_cards += 1
    report["scorecards"] = n_cards
    return report


def collect(code: str = "CT", years: list[int] | None = None) -> list[dict[str, Any]]:
    reg = load_registry()[code]
    collector = BaseCollector()
    have = {
        p.stem for p in (ROOT / "data" / "raw" / "competitions" / "cricsheet" / code).glob("*.json")
    }
    reports = []
    for e in reg["editions"]:
        if not e.get("espn_series") or (years and e["year"] not in years):
            continue
        if collector.is_stopped:
            print("collector stopped:", collector.stop_reason)
            break
        print(f"{code} {e['year']} ...")
        r = collect_edition(collector, code, e, have, all_scorecards=True)
        print("  ", r)
        reports.append(r)
    return reports


if __name__ == "__main__":
    import sys

    collect(sys.argv[1] if len(sys.argv) > 1 else "CT")
