"""Load ball-by-ball for World Cup / Champions Trophy ODIs that Cricsheet withholds (Afghanistan men's matches),
from the Kaggle dataset "ODI ball by ball 2003 to 2025" (a copy of Cricsheet data, CC0 on Kaggle).

Safety rules (nothing is guessed):
  * a match is only written when date + both teams match a completed ODI in our gold that has no ball-by-ball;
  * every innings total (batter runs + extras) must equal our scorecard innings total exactly, else the match is skipped;
  * files go to data/raw/commentary/cricsheet/odi/<our match id>.json in Cricsheet JSON layout and are never
    written over an existing file.

Usage: python scripts/import_kaggle_odi_bbb.py <ODI_ball_by_ball_updated.csv> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "commentary" / "cricsheet" / "odi"
GOLD = ROOT / "data" / "warehouse" / "cricket_gold.duckdb"
GOLD_CT = ROOT / "data" / "warehouse" / "cricket_gold_ct.duckdb"


def num(v) -> int:
    return 0 if pd.isna(v) else int(v)


def build_json(g: pd.DataFrame, info: dict) -> dict:
    innings = []
    for inn, gi in g.groupby("innings", sort=True):
        team = gi["batting_team"].iloc[0]
        overs: dict[int, list] = {}
        for r in gi.itertuples(index=False):
            ov = int(str(r.ball).split(".")[0])
            extras = {k: num(getattr(r, k)) for k in ("wides", "noballs", "byes", "legbyes", "penalty") if num(getattr(r, k))}
            ex_key = {"wides": "wides", "noballs": "noballs", "byes": "byes", "legbyes": "legbyes", "penalty": "penalty"}
            d = {
                "batter": r.striker,
                "bowler": r.bowler,
                "non_striker": r.non_striker,
                "runs": {"batter": num(r.runs_off_bat), "extras": num(r.extras), "total": num(r.runs_off_bat) + num(r.extras)},
            }
            if extras:
                d["extras"] = {ex_key[k]: v for k, v in extras.items()}
            if isinstance(r.wicket_type, str) and r.wicket_type:
                d["wickets"] = [{"player_out": r.player_dismissed, "kind": r.wicket_type}]
            overs.setdefault(ov, []).append(d)
        innings.append({"team": team, "overs": [{"over": o, "deliveries": ds} for o, ds in sorted(overs.items())]})
    return {"meta": {"data_version": "kaggle-odi-ball-by-ball-updated (copy of Cricsheet data)"}, "info": info, "innings": innings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = pd.read_csv(a.csv, low_memory=False)
    d["start_date"] = d["start_date"].astype(str)
    teams = d.groupby("match_id").apply(lambda x: frozenset(x.batting_team) | frozenset(x.bowling_team), include_groups=False)
    dates = d.groupby("match_id")["start_date"].first()

    OUT.mkdir(parents=True, exist_ok=True)
    wrote, skipped = [], []
    for path in (GOLD, GOLD_CT):
        c = duckdb.connect(str(path), read_only=True)
        m = c.execute(
            "select match_id, tournament_id, match_date, team1_name, team2_name from gold.fact_matches "
            "where is_completed and not has_ball_by_ball and format = 'ODI'"
        ).df()
        for r in m.itertuples():
            want = frozenset([r.team1_name, r.team2_name])
            ids = [k for k in dates.index if dates[k] == str(r.match_date)[:10] and teams[k] == want]
            if len(ids) != 1:
                continue
            kid = ids[0]
            g = d[d.match_id == kid]
            kt = {int(i): num(gi.runs_off_bat.sum()) + num(gi.extras.sum()) for i, gi in g.groupby("innings")}
            gold_inn = c.execute(
                "select innings_number, total_runs from gold.fact_innings where match_id = ? and not coalesce(is_super_over, false)",
                (r.match_id,),
            ).fetchall()
            gt = {int(i): int(t) for i, t in gold_inn}
            if kt != gt:
                skipped.append((r.match_id, f"innings totals differ kaggle={kt} gold={gt}"))
                continue
            out = OUT / f"{r.match_id}.json"
            if out.exists():
                skipped.append((r.match_id, "file already exists"))
                continue
            info = {
                "dates": [str(r.match_date)[:10]],
                "teams": [r.team1_name, r.team2_name],
                "match_type": "ODI",
                "gender": "male",
                "event": {"name": r.tournament_id},
                "venue": g["venue"].iloc[0],
                "kaggle_match_id": str(kid),
                "source_note": "Kaggle 'ODI ball by ball 2003 to 2025' (CC0); Cricsheet withholds Afghanistan men's matches",
            }
            if not a.dry_run:
                out.write_text(json.dumps(build_json(g, info)), encoding="utf-8")
            wrote.append((r.match_id, r.tournament_id, str(r.match_date)[:10], r.team1_name, r.team2_name, len(g)))
    for w in wrote:
        print("OK  ", *w)
    for s in skipped:
        print("SKIP", *s)
    print(f"{len(wrote)} matches {'would be ' if a.dry_run else ''}written, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
