# ruff: noqa: E501
"""Champions Trophy and World Test Championship: raw files -> silver -> gold -> DuckDB, plus a coverage report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.competitions import fetch as fetch_mod
from src.competitions.silver_cricsheet import ROOT, build_competition, load_registry
from src.transformations.gold import build_gold
from src.warehouse.load_gold import load_duckdb

OUT = ROOT / "data" / "competitions"
WAREHOUSE = ROOT / "data" / "warehouse"


def run(
    codes: tuple[str, ...] = ("CT", "WTC", "ASIA", "WC27"),
    download: bool = True,
    force_download: bool = False,
) -> dict:
    registry = load_registry()
    summary: dict = {"started": datetime.now(UTC).isoformat(), "competitions": {}}
    played = tuple(c for c in codes if c != "WC27")
    if (
        "WC27" in codes
    ):  # the upcoming 2027 World Cup: published schedule, venues, teams (no results)
        from src.competitions import world_cup_2027

        summary["wc27"] = world_cup_2027.build_all()
    if played:
        fetch_mod.download(force_download if download else False)
        from src.competitions import espn

        for code in played:
            espn.collect(
                code
            )  # polite, cached: abandoned matches, squads, points tables, 2002, Test cycle membership
        fetch_mod.select()
    for code in played:
        silver = build_competition(code)
        root = OUT / code.lower()
        gold = build_gold(root)
        duck = WAREHOUSE / f"cricket_gold_{code.lower()}.duckdb"
        counts = load_duckdb(root, duck, skip_missing=True)
        matches = pd.read_parquet(root / "data" / "gold" / "fact_matches" / "part-0.parquet")
        per_year = matches.groupby("year").size().to_dict()
        gaps = []
        for e in registry[code]["editions"]:
            have = int(per_year.get(e["year"], 0))
            if e.get("source") == "unavailable":
                gaps.append(
                    {
                        "year": e["year"],
                        "have": 0,
                        "scheduled": None,
                        "note": "no open data source; not loadable automatically",
                    }
                )
            elif e.get("scheduled_matches") and have < e["scheduled_matches"]:
                gaps.append(
                    {
                        "year": e["year"],
                        "have": have,
                        "scheduled": e["scheduled_matches"],
                        "note": "Cricsheet omits abandoned / no-result matches (and some others)",
                    }
                )
        summary["competitions"][code] = {
            "silver_rows": silver["rows"],
            "gold_rows": {k: v["rows"] for k, v in gold.items()},
            "duckdb": str(duck.relative_to(ROOT)),
            "duckdb_rows": counts,
            "matches_per_year": {int(k): int(v) for k, v in per_year.items()},
            "coverage_gaps": gaps,
        }
    summary["finished"] = datetime.now(UTC).isoformat()
    if played:
        write_report(summary)
    return summary


def write_report(summary: dict) -> Path:
    lines = [
        "# Champions Trophy and World Test Championship data",
        "",
        f"Built: {summary['finished']}",
        "",
    ]
    for code, s in summary["competitions"].items():
        lines += [f"## {code}", "", "| year | matches in data |", "|---|---|"]
        lines += [f"| {y} | {n} |" for y, n in sorted(s["matches_per_year"].items())]
        lines += [
            "",
            "Rows (gold): "
            + ", ".join(
                f"{k} {v}" for k, v in s["gold_rows"].items() if k.startswith(("fact_", "dim_"))
            ),
            "",
        ]
        if s["coverage_gaps"]:
            lines += ["Known gaps:", ""]
            for g in s["coverage_gaps"]:
                have = f"{g['have']} of {g['scheduled']}" if g["scheduled"] else "none"
                lines.append(f"- {g['year']}: {have} matches ({g['note']})")
            lines.append("")
    lines += [
        "No 2026 Champions Trophy exists (the next edition is 2029). The 2025-27 World Test Championship cycle is in progress (no final yet); 5 matches of the 2019-21 cycle were postponed and never played.",
        "",
    ]
    out = ROOT / "reports" / "competitions_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "reports" / "competitions_summary.json").write_text(
        json.dumps(summary, indent=1, default=str), encoding="utf-8"
    )
    return out
