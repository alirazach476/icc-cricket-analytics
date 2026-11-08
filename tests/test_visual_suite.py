# ruff: noqa: E501
"""The visualisation suite: every required chart that the data supports is present and every page renders without errors."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = r"""
import json
from server import runner

def titles(nodes, acc):
    for n in nodes or []:
        if n["t"] == "plot":
            t = n["fig"]["layout"].get("title")
            acc["plots"].append((t.get("text") if isinstance(t, dict) else t) or "")
        if n["t"] == "alert" and n["kind"] == "error":
            acc["errors"].append(n["text"][-200:])
        if n["t"] == "tabs":
            for items in n["items"]:
                titles(items, acc)
        for x in n.get("items") or []:
            if isinstance(x, list):
                titles(x, acc)

out = {}
for comp, slugs in (("wc", ["home", "tournaments", "players", "teams", "matches", "ball-by-ball", "research", "ml", "data"]),
                    ("ct", ["home", "tournaments", "teams", "ball-by-ball"]), ("wtc", ["home", "tournaments", "teams", "ball-by-ball"])):
    for slug in slugs:
        d = json.loads(runner.run_page(slug, {}, None, comp))
        acc = {"plots": [], "errors": []}
        titles(d["body"], acc)
        out[f"{comp}/{slug}"] = acc
print(json.dumps(out))
"""

REQUIRED = {
    "wc/home": ["Matches played by edition and format", "Participating teams by edition", "Champions timeline"],
    "wc/tournaments": ["Centuries and half-centuries", "Boundaries: fours and sixes", "Runs against balls faced", "Runs by player and tournament", "Batting average by edition", "Bowling average against strike rate", "Overs, runs conceded and wickets", "Economy rate by player and edition", "Economy rate distribution by edition", "Strike rate distribution by edition", "Dot balls bowled", "Maiden overs", "Top run scorers", "Top wicket takers"],
    "wc/teams": ["results by match stage", "Average runs scored per innings, by edition", "Win % by edition"],
    "wc/ball-by-ball": ["Batter v bowler strike rate", "Every matchup", "Run progression", "Dot-ball % by phase"],
    "wc/research": ["mean first-innings total by stage group", "batting-first win rate by stage group", "Residuals against fitted", "Residuals of the trend line", "Feature correlations"],
    "wc/ml": ["Precision-recall curve", "Learning curve", "Prediction error", "Error distribution", "SHAP dependence", "Actual against predicted first-innings score", "ROC curves", "Calibration"],
    "wc/data": ["Processing time of each pipeline run", "Duplicate records by table", "Missing values in fact_matches"],
}


@pytest.fixture(scope="module")
def probe() -> dict:
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, capture_output=True, text=True, timeout=1500)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_no_page_raises_an_error(probe: dict) -> None:
    assert {k: v["errors"] for k, v in probe.items() if v["errors"]} == {}


@pytest.mark.parametrize("page", sorted(REQUIRED))
def test_required_charts_are_present(probe: dict, page: str) -> None:
    have = [t.replace("<br>", " ") for t in probe[page]["plots"]]
    missing = [t for t in REQUIRED[page] if not any(t in h for h in have)]
    assert not missing, (page, missing)


@pytest.mark.parametrize("comp", ["ct", "wtc"])
def test_new_competition_pages_have_the_extra_batting_bowling_and_stage_charts(probe: dict, comp: str) -> None:
    have = " | ".join(probe[f"{comp}/tournaments"]["plots"] + probe[f"{comp}/teams"]["plots"])
    for t in ("Bowling average against strike rate", "Economy rate by player and edition", "results by match stage"):
        assert t in have, (comp, t)
