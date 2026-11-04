"""Collect points tables (standings) and tournament squads from ESPNcricinfo.

Uses the shared BaseCollector (robots.txt check, throttling, hard stop on 401/403/429,
raw HTML caching). Raw HTML goes to ``data/raw/standings|squads/<tournament_id>/`` and
normalized JSON to ``data/processed/standings|squads/<tournament_id>.json``.
"""

from __future__ import annotations

import csv
import json
from typing import Any

from src.collectors.base_collector import BaseCollector
from src.collectors.scorecard_collector import load_match_manifest
from src.parsers.standings_parser import (
    derive_qualification,
    parse_squad_html,
    parse_squad_index_html,
    parse_standings_html,
)
from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

ESPN_ORIGIN = "https://www.espncricinfo.com"


def load_tournament_urls() -> dict[str, str]:
    path = get_project_root() / "data" / "manifests" / "tournaments.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["tournament_id"]: row["source_url"].rstrip("/")
            for row in csv.DictReader(handle)
            if row.get("source_url")
        }


def _write_json(path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def collect_standings(
    collector: BaseCollector, tournament_id: str, series_url: str, *, force: bool = False
) -> dict[str, Any]:
    root = get_project_root()
    url = f"{series_url}/points-table-standings"
    raw_rel = f"data/raw/standings/{tournament_id}"
    html_path = root / raw_rel / "standings.html"

    fetch = collector.fetch_html(url, allow_cache_path=None if force else html_path)
    report: dict[str, Any] = {"tournament_id": tournament_id, "url": url, "status": fetch.access_status}
    if not fetch.ok or not fetch.content:
        report["error"] = fetch.error
        return report
    if not fetch.from_cache:
        if force and html_path.exists():
            html_path.unlink()
        collector.save_raw_text(
            raw_rel,
            "standings.html",
            fetch.content,
            metadata={"tournament_id": tournament_id, "source_url": url},
        )

    parsed = parse_standings_html(fetch.content, tournament_id=tournament_id, source_url=url)
    manifest = [m for m in load_match_manifest() if m.get("tournament_id") == tournament_id]
    parsed["qualification"] = derive_qualification(parsed["rows"], manifest)
    parsed["collected_at"] = utc_now_iso()
    _write_json(root / "data" / "processed" / "standings" / f"{tournament_id}.json", parsed)
    report.update(
        parse_status=parsed["parse_status"],
        rows=len(parsed["rows"]),
        groups=len({r["group_name"] for r in parsed["rows"]}),
        warnings=parsed["warnings"],
    )
    return report


def collect_squads(
    collector: BaseCollector, tournament_id: str, series_url: str, *, force: bool = False
) -> dict[str, Any]:
    root = get_project_root()
    index_url = f"{series_url}/squads"
    raw_rel = f"data/raw/squads/{tournament_id}"
    index_path = root / raw_rel / "squads_index.html"

    fetch = collector.fetch_html(index_url, allow_cache_path=None if force else index_path)
    report: dict[str, Any] = {"tournament_id": tournament_id, "url": index_url, "status": fetch.access_status}
    if not fetch.ok or not fetch.content:
        report["error"] = fetch.error
        return report
    if not fetch.from_cache:
        if force and index_path.exists():
            index_path.unlink()
        collector.save_raw_text(
            raw_rel,
            "squads_index.html",
            fetch.content,
            metadata={"tournament_id": tournament_id, "source_url": index_url},
        )

    links = parse_squad_index_html(fetch.content)
    squads: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for link in links:
        if collector.is_stopped:
            failures.append({"url": link, "error": collector.stop_reason or "stopped"})
            continue
        squad_url = f"{ESPN_ORIGIN}{link}"
        slug = link.rstrip("/").split("/")[-2]
        squad_path = root / raw_rel / f"{slug}.html"
        res = collector.fetch_html(squad_url, allow_cache_path=None if force else squad_path)
        if not res.ok or not res.content:
            failures.append({"url": squad_url, "error": res.error or res.access_status})
            continue
        if not res.from_cache:
            if force and squad_path.exists():
                squad_path.unlink()
            collector.save_raw_text(
                raw_rel,
                f"{slug}.html",
                res.content,
                metadata={"tournament_id": tournament_id, "source_url": squad_url},
            )
        parsed = parse_squad_html(res.content, tournament_id=tournament_id, source_url=squad_url)
        if parsed["parse_status"] != "ok":
            failures.append({"url": squad_url, "error": "; ".join(parsed["warnings"]) or parsed["parse_status"]})
            continue
        squads.append(parsed)

    payload = {
        "tournament_id": tournament_id,
        "source_name": "ESPNcricinfo",
        "source_url": index_url,
        "collected_at": utc_now_iso(),
        "squad_links_found": len(links),
        # Cricinfo lists replaced/withdrawn players alongside the final squad; the
        # per-player is_withdrawn flag separates them.
        "active_players": sum(1 for s in squads for p in s["players"] if not p["is_withdrawn"]),
        "squads": squads,
        "failures": failures,
    }
    _write_json(root / "data" / "processed" / "squads" / f"{tournament_id}.json", payload)
    report.update(
        squad_links=len(links),
        squads=len(squads),
        players=sum(len(s["players"]) for s in squads),
        failures=failures,
    )
    return report


def collect_standings_and_squads(
    *,
    tournament_id: str | None = None,
    what: tuple[str, ...] = ("standings", "squads"),
    force: bool = False,
) -> dict[str, Any]:
    urls = load_tournament_urls()
    if tournament_id:
        if tournament_id not in urls:
            raise ValueError(f"Unknown tournament_id: {tournament_id}")
        urls = {tournament_id: urls[tournament_id]}

    collector = BaseCollector()
    started = utc_now_iso()
    results: list[dict[str, Any]] = []
    for tid, series_url in urls.items():
        entry: dict[str, Any] = {"tournament_id": tid}
        if "standings" in what and not collector.is_stopped:
            entry["standings"] = collect_standings(collector, tid, series_url, force=force)
        if "squads" in what and not collector.is_stopped:
            entry["squads"] = collect_squads(collector, tid, series_url, force=force)
        results.append(entry)
        if collector.is_stopped:
            logger.error("Stopping: %s", collector.stop_reason)
            break
    return {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "stopped": collector.is_stopped,
        "stop_reason": collector.stop_reason,
        "results": results,
    }
