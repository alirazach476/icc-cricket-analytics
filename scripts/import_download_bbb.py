"""Load ball-by-ball CSVs supplied by the user (Downloads folder) for matches Cricsheet withholds.

Two layouts are understood:
  * "cricsheet-style" (cwc 2023.csv): striker, non_striker, runs_off_bat, wides/noballs/byes/legbyes/penalty
  * "team-code style" (t20_wc_*_deliveries.csv, ct_*_deliveries.csv): batting_team/bowling_team are codes (AFG, RSA ...),
    runs_of_bat, wide/legbyes/byes/noballs, fielder; no non-striker (written as unknown)

A match is written only when date + both teams match a completed match of ours that has no ball-by-ball AND every innings
total (batter runs + extras) equals our scorecard innings total exactly. Anything else is reported and skipped.
Files are never written over an existing file.

Usage: python scripts/import_download_bbb.py <csv> <T20|ODI> <gold db name, e.g. cricket_gold> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CODES = {
    "AFG": "Afghanistan", "AUS": "Australia", "BAN": "Bangladesh", "ENG": "England", "IND": "India", "IRE": "Ireland",
    "NAM": "Namibia", "NED": "Netherlands", "NZ": "New Zealand", "PAK": "Pakistan", "SA": "South Africa", "RSA": "South Africa",
    "SL": "Sri Lanka", "SCO": "Scotland", "UGA": "Uganda", "USA": "United States of America", "WI": "West Indies",
    "PNG": "Papua New Guinea", "OMAN": "Oman", "OMN": "Oman", "CAN": "Canada", "UAE": "United Arab Emirates",
    "ZIM": "Zimbabwe", "NEP": "Nepal", "ITA": "Italy", "HK": "Hong Kong",
}


def num(v) -> int:
    return 0 if pd.isna(v) else int(v)


def normalise(d: pd.DataFrame) -> pd.DataFrame:
    if "runs_of_bat" in d.columns:  # team-code layout
        out = pd.DataFrame({
            "match_id": d["match_id"], "date": pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d"), "venue": d["venue"],
            "innings": d["innings"], "ball": d["over"],
            "batting_team": d["batting_team"].map(lambda c: CODES.get(c, c)),
            "bowling_team": d["bowling_team"].map(lambda c: CODES.get(c, c)),
            "striker": d["striker"], "non_striker": None, "bowler": d["bowler"],
            "runs_off_bat": d["runs_of_bat"], "extras": d["extras"], "wides": d["wide"], "noballs": d["noballs"],
            "byes": d["byes"], "legbyes": d["legbyes"], "penalty": 0,
            "wicket_type": d["wicket_type"], "player_dismissed": d["player_dismissed"], "fielder": d.get("fielder"),
        })
    else:
        out = d.rename(columns={"start_date": "date"}).copy()
        out["fielder"] = None
    return out


def _tokens(name: str) -> list[str]:
    return [t.lower().strip(".,") for t in str(name).replace("-", " ").split() if t.strip()]


def resolve(raw: str, roster: list[str]) -> str | None:
    """Map a file name (surname, given name or 'AB Surname') to exactly one roster player, else None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    rt = _tokens(raw)
    exact = [n for n in roster if _tokens(n) == rt]
    if len(exact) == 1:
        return exact[0]
    parts = str(raw).split()
    initials = parts[0] if len(parts) > 1 and parts[0].isupper() and parts[0].isalpha() and len(parts[0]) <= 5 else None
    sur = _tokens(" ".join(parts[1:])) if initials else rt

    def fits(full: str) -> bool:
        ft = _tokens(full)
        if not ft or not all(t in ft for t in sur):
            return False
        if initials and not ft[0].startswith(initials[0].lower()):
            return False
        return True
    hits = [n for n in roster if fits(n)]
    if len(hits) == 1:
        return hits[0]
    if hits:
        return None
    # fallback 1: a distinctive name token (>= 4 letters) that appears in exactly one roster name
    words = [t for t in rt if len(t) >= 4]
    for t in sorted(words, key=len, reverse=True):
        h = [n for n in roster if t in _tokens(n)]
        if len(h) == 1:
            return h[0]
    # fallback 2: spelling variants (Liton/Litton, Shenwari/Shinwari) - unique close match on a token
    import difflib
    for t in sorted(words, key=len, reverse=True):
        h = [n for n in roster if difflib.get_close_matches(t, [x for x in _tokens(n) if len(x) >= 4], n=1, cutoff=0.82)]
        if len(h) == 1:
            return h[0]
    return None


def build_json(g: pd.DataFrame, info: dict) -> dict:
    innings = []
    for inn, gi in g.groupby("innings", sort=True):
        overs: dict[int, list] = {}
        for r in gi.itertuples(index=False):
            ov = int(str(r.ball).split(".")[0])
            extras = {k: num(getattr(r, k)) for k in ("wides", "noballs", "byes", "legbyes", "penalty") if num(getattr(r, k))}
            d = {"batter": r.striker, "bowler": r.bowler,
                 "runs": {"batter": num(r.runs_off_bat), "extras": num(r.extras), "total": num(r.runs_off_bat) + num(r.extras)}}
            if isinstance(r.non_striker, str):
                d["non_striker"] = r.non_striker
            if extras:
                d["extras"] = extras
            if isinstance(r.wicket_type, str) and r.wicket_type:
                w = {"player_out": r.player_dismissed, "kind": r.wicket_type}
                if isinstance(r.fielder, str) and r.fielder:
                    w["fielders"] = [{"name": r.fielder}]
                d["wickets"] = [w]
            overs.setdefault(ov, []).append(d)
        innings.append({"team": gi["batting_team"].iloc[0], "overs": [{"over": o, "deliveries": ds} for o, ds in sorted(overs.items())]})
    return {"meta": {"data_version": "user-supplied ball-by-ball CSV"}, "info": info, "innings": innings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("fmt", choices=("T20", "ODI"))
    ap.add_argument("db")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = normalise(pd.read_csv(a.csv, low_memory=False))
    out_dir = ROOT / "data" / "raw" / "commentary" / "cricsheet" / a.fmt.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(str(ROOT / "data" / "warehouse" / f"{a.db}.duckdb"), read_only=True)
    m = c.execute(
        "select match_id, tournament_id, match_date, team1_name, team2_name from gold.fact_matches "
        "where is_completed and not has_ball_by_ball and format = ?", (a.fmt,)
    ).df()
    wrote, skipped = [], []
    for r in m.itertuples():
        want = frozenset([r.team1_name, r.team2_name])
        s = d[d["date"] == str(r.match_date)[:10]]
        keys = [k for k, gm in s.groupby("match_id") if frozenset(gm.batting_team) | frozenset(gm.bowling_team) == want]
        if len(keys) != 1:
            continue
        g = s[s.match_id == keys[0]]
        kt = {int(i): num(gi.runs_off_bat.sum()) + num(gi.extras.sum()) for i, gi in g.groupby("innings")}
        gt = {int(i): int(t) for i, t in c.execute(
            "select innings_number, total_runs from gold.fact_innings where match_id = ? and not coalesce(is_super_over, false)", (r.match_id,)).fetchall()}
        if kt != gt:
            skipped.append((r.match_id, f"{r.team1_name} v {r.team2_name}", f"innings totals differ file={kt} gold={gt}"))
            continue
        ros = c.execute(
            "select t.team_name, p.full_name from gold.fact_player_performances f join gold.dim_players p on p.player_id = f.player_id "
            "join gold.dim_teams t on t.team_id = f.team_id where f.match_id = ?", (r.match_id,)).fetchall()
        roster = {}
        for tn, nm in ros:
            roster.setdefault(tn, []).append(nm)
        cache, bad = {}, set()

        def fix(raw, team):
            key = (raw, team)
            if key not in cache:
                cache[key] = resolve(raw, roster.get(team, []))
            if cache[key] is None and isinstance(raw, str) and raw.strip():
                bad.add(f"{raw} ({team})")
            return cache[key] if cache[key] is not None else raw

        g = g.copy()
        g["striker"] = [fix(n, t) for n, t in zip(g.striker, g.batting_team)]
        g["bowler"] = [fix(n, t) for n, t in zip(g.bowler, g.bowling_team)]
        g["player_dismissed"] = [fix(n, t) if isinstance(n, str) else n for n, t in zip(g.player_dismissed, g.batting_team)]
        if "non_striker" in g and g["non_striker"].notna().any():
            g["non_striker"] = [fix(n, t) if isinstance(n, str) else n for n, t in zip(g.non_striker, g.batting_team)]
        # two different file names must never collapse into one player
        for tm in {t for _, t in cache}:
            tgt = [v for (k, t), v in cache.items() if t == tm and v is not None]
            if len(tgt) != len(set(tgt)):
                bad.add(f"two names resolve to one player ({tm})")
        if bad:
            skipped.append((r.match_id, f"{r.team1_name} v {r.team2_name}", "unresolved names: " + ", ".join(sorted(bad))))
            continue
        out = out_dir / f"{r.match_id}.json"
        if out.exists():
            skipped.append((r.match_id, "", "file already exists"))
            continue
        info = {"dates": [str(r.match_date)[:10]], "teams": [r.team1_name, r.team2_name], "match_type": a.fmt, "gender": "male",
                "event": {"name": r.tournament_id}, "venue": g["venue"].iloc[0],
                "source_note": f"user-supplied CSV {Path(a.csv).name}; Cricsheet withholds Afghanistan men's matches"}
        if not a.dry_run:
            out.write_text(json.dumps(build_json(g, info)), encoding="utf-8")
        wrote.append((r.match_id, r.tournament_id, str(r.match_date)[:10], r.team1_name, r.team2_name))
    for w in wrote:
        print("OK  ", *w)
    for s in skipped:
        print("SKIP", *s)
    print(f"{len(wrote)} written, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
