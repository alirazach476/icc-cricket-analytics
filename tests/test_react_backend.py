# ruff: noqa: E501
"""The React dashboard's backend runs the real page scripts through a Streamlit shim.

These tests run in a subprocess because the shim replaces ``sys.modules['streamlit']``, which must not
leak into the Streamlit AppTest based tests in the same pytest process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PROBE = r"""
import json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from server import runner, api, editions

def walk(nodes, acc):
    for n in nodes:
        acc.append(n)
        if n["t"] in ("tabs", "cols"):
            for it in n["items"]:
                walk(it, acc)
        elif n["t"] in ("expander", "box"):
            walk(n["items"], acc)
    return acc

def page(slug, state=None, ed=None, comp="wc"):
    d = json.loads(runner.run_page(slug, state or {}, ed, comp))
    return d, walk(d["sidebar"], []) + walk(d["body"], [])

out = {"pages": {}}
for slug in runner.COMPETITION_PAGES["wc"]:
    d, nodes = page(slug)
    out["pages"][slug] = {
        "plots": sum(n["t"] == "plot" for n in nodes),
        "errors": [n["text"][:300] for n in nodes if n["t"] == "alert" and n["kind"] == "error"],
        "unsupported": d["unsupported"],
        "hero": bool(d["hero"]),
        "leak": any("DeltaGenerator" in json.dumps(n) for n in nodes),
        "tab_labels": [n["labels"] for n in nodes if n["t"] == "tabs"],
        "template_in_fig": any("template" in n["fig"]["layout"] for n in nodes if n["t"] == "plot"),
    }

alle = api.meta_editions()
eds = {e["id"]: e for e in alle if e["competition"] == "wc"}
out["competitions"] = {c["code"]: {"editions": [e["id"] for e in c["editions"]], "pages": c["pages"], "logos": [e["logo"] for e in c["editions"]]} for c in api._META["competitions"]}
out["other_pages"] = {}
for code in ("ct", "wtc", "wc27"):
    for slug in runner.COMPETITION_PAGES[code]:
        d, nodes = page(slug, comp=code)
        out["other_pages"][f"{code}/{slug}"] = {"errors": [n["text"][:300] for n in nodes if n["t"] == "alert" and n["kind"] == "error"], "plots": sum(n["t"] == "plot" for n in nodes), "world_cup_text": any("World Cup" in json.dumps(n) for n in nodes if n["t"] in ("md", "caption", "h3", "metric", "alert"))}
out["de_checks"] = {}
for code in ("ct", "wtc"):
    d, nodes = page("data", comp=code)
    for n in nodes:
        if n["t"] == "table" and "status" in n["columns"]:
            out["de_checks"][code] = [r[n["columns"].index("status")] for r in n["rows"]]
out["editions"] = {k: {"logo": v["logo"], "chart": len(v["theme"]["chart"]), "start": v["start"], "end": v["end"]} for k, v in eds.items()}

# edition drives the tournament widgets
d, nodes = page("tournaments", ed=eds["t20-2021"])
out["t_widgets"] = {w["label"]: w["value"] for w in nodes if w["t"] == "w"}
d, nodes = page("matches", ed=eds["odi-2015"])
ws = {w["label"]: w for w in nodes if w["t"] == "w"}
out["m_tournament"] = ws["Tournament"]["value"]
out["m_dates"] = [o["v"][:10] for o in ws["Match"]["options"]]
# ball-by-ball with an edition that has data narrows the list too
d, nodes = page("ball-by-ball", ed=eds["odi-2007"])
ws = {w["label"]: w for w in nodes if w["t"] == "w"}
out["b_dates"] = [o["v"][:10] for o in ws["Match (ball-by-ball available)"]["options"]]

# widget state round trip
d, nodes = page("tournaments")
fmt = next(w for w in nodes if w["t"] == "w" and w["label"] == "Format")
d2, nodes2 = page("tournaments", {fmt["id"]: "T20"})
out["roundtrip"] = {w["label"]: w["value"] for w in nodes2 if w["t"] == "w"}
# clicking a result opens the match
d, nodes = page("tournaments", ed=eds["odi-2011"])
res = next(n for n in nodes if n["t"] == "table" and "stage" in n["columns"] and n.get("links"))
mid = res["links"][10]
out["link_cols"] = res["columns"]
d, nodes = page("matches", {"__session": {"focus_match": mid}})
ws = {w["label"]: w["value"] for w in nodes if w["t"] == "w"}
out["focus"] = ws
d, nodes = page("matches", {"__session": {"focus_match": mid}}, eds["odi-2011"])
out["focus_with_edition"] = {w["label"]: w["value"] for w in nodes if w["t"] == "w"}
out["synthetic_text"] = any("SYNTHETIC" in json.dumps(n) or "is_synthetic" in json.dumps(n) for n in nodes)
print("PROBE" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    if not (ROOT / "data" / "warehouse" / "cricket_gold.duckdb").exists():
        pytest.skip("gold database not built")
    r = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", PROBE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith("PROBE"))
    return json.loads(line[5:])


def test_every_page_renders_without_errors(probe: dict) -> None:
    assert len(probe["pages"]) == 11
    for slug, p in probe["pages"].items():
        assert not p["errors"], (slug, p["errors"])
        assert not p["unsupported"], (slug, p["unsupported"])
        assert p["hero"], slug
        assert not p["leak"], slug
        assert not p["template_in_fig"], slug


def test_react_has_every_chart_of_the_streamlit_app(probe: dict) -> None:
    assert sum(p["plots"] for p in probe["pages"].values()) >= 190


def test_react_has_the_same_tabs_as_streamlit(probe: dict) -> None:
    labels = {
        slug: [x for tabs in p["tab_labels"] for x in tabs] for slug, p in probe["pages"].items()
    }
    assert "Squad" in labels["squads"] and "Player lookup" in labels["squads"]
    assert "Match explorer" in labels["matches"] and "Venues" in labels["matches"]
    assert "Importance and SHAP" in labels["ml"] and "Model comparison" in labels["ml"]
    assert "Lineage" in labels["data"] and "Coverage" in labels["data"]


def test_each_world_cup_has_a_logo_and_theme(probe: dict) -> None:
    assert len(probe["editions"]) == 17
    for eid, e in probe["editions"].items():
        assert (ROOT / "web" / "public" / e["logo"].lstrip("/")).exists(), eid
        assert e["chart"] == 8
        assert e["start"] <= e["end"]


def test_selected_world_cup_drives_the_filters(probe: dict) -> None:
    assert probe["t_widgets"]["Format"] == "T20"
    assert str(probe["t_widgets"]["Tournament year"]) == "2021"
    assert probe["m_tournament"] == "ICC Cricket World Cup 2015"
    assert probe["m_dates"] and all("2015-02-14" <= d <= "2015-03-29" for d in probe["m_dates"])
    assert probe["b_dates"] and all("2007-03-13" <= d <= "2007-04-28" for d in probe["b_dates"])


def test_widget_values_round_trip(probe: dict) -> None:
    assert probe["roundtrip"]["Format"] == "T20"


def test_result_rows_open_the_match(probe: dict) -> None:
    assert "match_id" not in probe["link_cols"]
    for f in (probe["focus"], probe["focus_with_edition"]):
        assert f["Tournament"] == "ICC Cricket World Cup 2011"
        assert f["Match"] == "2011-02-27  India v England  (Group Stage)"


def test_synthetic_wording_is_not_shown(probe: dict) -> None:
    assert probe["synthetic_text"] is False


def test_champions_trophy_and_test_championship_are_in_the_switcher(probe: dict) -> None:
    c = probe["competitions"]
    assert set(c) == {"wc", "wc27", "ct", "wtc"}
    # 2027 is an (upcoming) edition in the ODI World Cup rail, not a separate tab
    assert c["wc"]["editions"][-1] == "wc27-2027" and c["wc27"]["pages"] == ["home"]
    assert c["wc27"]["editions"] == []
    assert c["ct"]["editions"] == [
        "ct-2002",
        "ct-2004",
        "ct-2006",
        "ct-2009",
        "ct-2013",
        "ct-2017",
        "ct-2025",
    ]
    assert c["wtc"]["editions"] == ["wtc-2021", "wtc-2023", "wtc-2025", "wtc-2027"]
    assert (
        "ml" in c["ct"]["pages"]
        and "data" in c["wtc"]["pages"]
        and "research" not in c["wtc"]["pages"]
        and "insights" in c["ct"]["pages"]
    )
    assert "squads" in c["ct"]["pages"] and "ball-by-ball" in c["wtc"]["pages"]


def test_new_competition_pages_render_without_errors(probe: dict) -> None:
    for name, p in probe["other_pages"].items():
        assert not p["errors"], (name, p["errors"])
        assert p["plots"] >= 1, name
        assert name.startswith("wc27") or not p["world_cup_text"], (
            name
        )  # wording is adapted to the competition


def test_competition_data_engineering_checks_all_pass(probe: dict) -> None:
    """The Champions Trophy and Test Championship Data Engineering pages reconcile their own gold data."""
    for code in ("ct", "wtc"):
        assert probe["de_checks"][code] == ["pass"] * 9, code
