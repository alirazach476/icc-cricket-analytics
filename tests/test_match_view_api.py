"""/api/match/<id>: one call returns the scoreboard, charts, the tournament's branding and the neighbouring matches."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = r"""
import json
from fastapi.testclient import TestClient
from server.api import app
from app.utils import database as d
c = TestClient(app)
out = {}
for comp, q in (
    ("wc", "select match_id from gold.fact_matches where has_ball_by_ball and format='T20' order by match_date desc limit 1"),
    ("wtc", "select match_id from gold.fact_matches order by match_date limit 1"),
    ("ct", "select match_id from gold.fact_matches where margin_type='abandoned' limit 1"),
):
    d.set_competition(comp)
    mid = d.run(q).iloc[0, 0]
    r = c.get(f"/api/match/{mid}?competition={comp}")
    b = r.json()
    p = b["payload"]
    out[comp] = {"status": r.status_code, "edition": p["edition"], "kind": p["result_kind"], "groups": [g["group"] for g in b["charts"]],
                 "figs": sum(len(g["figs"]) for g in b["charts"]), "nb": b["neighbours"], "cache": r.headers.get("cache-control"),
                 "teams": [t["name"] for t in p["teams"]]}
out["missing"] = c.get("/api/match/nope?competition=wc").status_code
out["bad_comp"] = c.get("/api/match/1?competition=zzz").status_code
print(json.dumps(out, default=str))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_every_competition_returns_a_branded_scoreboard(probe: dict) -> None:
    for comp, prefix in (("wc", "t20-"), ("wtc", "wtc-"), ("ct", "ct-")):
        p = probe[comp]
        assert p["status"] == 200
        ed = p["edition"]
        assert ed["id"].startswith(prefix) and ed["logo"].startswith("/") and {"primary", "secondary", "tertiary", "bg"} <= set(ed["theme"])
        assert "max-age" in p["cache"]


def test_ball_by_ball_matches_come_with_charts_and_abandoned_ones_do_not(probe: dict) -> None:
    assert probe["wc"]["groups"] == ["Progression", "Overs and wickets", "Innings and chase", "Partnerships and wickets"] and probe["wc"]["figs"] >= 7
    assert probe["ct"]["kind"] == "abandoned" and probe["ct"]["figs"] == 0


def test_neighbouring_matches_and_error_codes(probe: dict) -> None:
    assert probe["wtc"]["nb"]["prev"] is None and probe["wtc"]["nb"]["next"]["id"]  # first match of a tournament
    assert probe["wc"]["nb"]["prev"]["label"]
    assert probe["missing"] == 404 and probe["bad_comp"] == 404
