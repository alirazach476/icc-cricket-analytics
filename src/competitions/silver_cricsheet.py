# ruff: noqa: E501
"""Cricsheet match files -> silver tables (the schema the existing gold builder reads).

Used for competitions that are not World Cups (Champions Trophy, World Test Championship final).
Each competition gets its own root ``data/competitions/<code>/`` so World Cup numbers never change;
``src.transformations.gold.build_gold(root)`` then builds its gold layer unchanged.

Facts (scores, wickets, overs, extras, winners, margins) come straight from the ball-by-ball file.
Nothing is invented: fields the source does not carry (captains, roles, birth dates for new players,
no-result matches that Cricsheet does not publish) stay empty and are listed in the coverage table.
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.parsers.ball_by_ball_parser import parse_cricsheet_match_json
from src.transformations.clean_deliveries import clean_delivery_list
from src.transformations.identity import RosterPlayer, cricsheet_slug, norm, resolve_name

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "competitions" / "cricsheet"
OUT = ROOT / "data" / "competitions"
SILVER = ROOT / "data" / "silver"

BOWLER_WICKETS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
NOT_OUT_KINDS = {"retired hurt", "retired not out"}
STAGE_MAP = {
    "Final": "Final",
    "Semi Final": "Semifinal",
    "Quarter Final": "Quarterfinal",
    "3rd Place Play-off": "Third place",
}
KNOCKOUT = {"Final", "Semifinal", "Quarterfinal", "Third place"}


def load_registry() -> dict:
    return yaml.safe_load((ROOT / "config" / "competitions.yaml").read_text(encoding="utf-8"))[
        "competitions"
    ]


def _overs_text(balls: int) -> float:
    return float(f"{balls // 6}.{balls % 6}")


# --------------------------------------------------------------------------- identities
class Identities:
    """Team and player ids: reuse the World Cup ids when the same team / player already exists."""

    def __init__(self) -> None:
        teams = pd.read_parquet(SILVER / "teams" / "part-0.parquet")
        self.team_rows = {r.team_name: r._asdict() for r in teams.itertuples(index=False)}
        self.new_teams: dict[str, dict] = {}
        players = pd.read_parquet(SILVER / "players" / "part-0.parquet")
        self.player_rows = players.set_index("player_id")
        imap = pd.read_parquet(SILVER / "player_identity_map" / "part-0.parquet")
        imap = imap[imap["resolved_player_id"].notna() & imap["source_name"].notna()]
        counts = imap.groupby("source_name")["resolved_player_id"].nunique()
        unique = imap[imap["source_name"].isin(counts[counts == 1].index)]
        self.name_to_player = dict(
            zip(unique["source_name"], unique["resolved_player_id"], strict=False)
        )
        self.new_players: dict[str, dict] = {}
        self._slug_owner: dict[str, str] = {}
        self.used_players: set[str] = set()
        self.team_names = {r.team_id: r.team_name for r in teams.itertuples(index=False)}
        # ESPNcricinfo scorecard rosters: Cricsheet names are resolved against the match's own roster
        self.match_roster: dict[str, list[RosterPlayer]] = {}
        self.current_mid: str | None = None
        self.extra_players: dict[str, dict] = {}
        self._resolved: dict[tuple, str | None] = {}

    def team_name(self, team_id: str) -> str | None:
        return self.team_names.get(team_id) or next(
            (t["team_name"] for t in self.new_teams.values() if t["team_id"] == team_id), None
        )

    def team(self, name: str) -> str:
        if name in self.team_rows:
            return self.team_rows[name]["team_id"]
        if name not in self.new_teams:
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            self.new_teams[name] = {
                "team_id": f"cricsheet_team_{slug}",
                "team_name": name,
                "short_name": "".join(w[0] for w in name.split()).upper()[:3],
                "source_team_id": None,
                "short_name_source": None,
                "team_key": norm(name),
            }
        return self.new_teams[name]["team_id"]

    def player(self, name: str, registry_id: str | None = None) -> str:
        roster = self.match_roster.get(self.current_mid or "")
        if roster:
            key = (self.current_mid, name)
            if key not in self._resolved:
                self._resolved[key] = resolve_name(name, roster)[0]
            if self._resolved[key]:
                self.used_players.add(self._resolved[key])
                return self._resolved[key]
        if name in self.name_to_player:
            pid = self.name_to_player[name]
        else:
            slug = cricsheet_slug(name)
            pid = f"cricsheet_{slug}"
            owner = self._slug_owner.setdefault(pid, registry_id or "")
            if registry_id and owner and owner != registry_id:
                pid = f"{pid}_{registry_id[:4]}"
            if pid not in self.new_players:
                self.new_players[pid] = {
                    "player_id": pid,
                    "full_name": name,
                    "batting_name": name,
                    "source_player_id": None,
                    "batting_style": None,
                    "bowling_style": None,
                    "date_of_birth": None,
                    "identity_source": "cricsheet_only",
                    "cricsheet_names": json.dumps([name]),
                    "cricsheet_ids": json.dumps([pid]),
                }
        self.used_players.add(pid)
        return pid

    def display_name(self, pid: str) -> str:
        if pid in self.player_rows.index:
            return str(self.player_rows.loc[pid, "full_name"])
        return self.new_players.get(pid, {}).get("full_name", pid)


# --------------------------------------------------------------------------- one match
def _wicket_credited_to_bowler(kind: str | None) -> bool:
    return kind in BOWLER_WICKETS


def build_match(doc: dict, ident: Identities, tournament_id: str, fmt: str) -> dict[str, Any]:
    info = doc["info"]
    mid = str(doc["_match_id"])
    ident.current_mid = mid
    people = (info.get("registry") or {}).get("people", {})
    teams = info["teams"]
    team_ids = {t: ident.team(t) for t in teams}
    parsed = parse_cricsheet_match_json(doc, match_id=mid, source_url=f"cricsheet://{mid}.json")
    deliveries = clean_delivery_list(parsed["deliveries"])
    pid = lambda n: ident.player(n, people.get(n)) if n else None  # noqa: E731

    innings_meta = doc.get("innings") or []
    inn_team = {i + 1: block.get("team") for i, block in enumerate(innings_meta)}
    inn_super = {i + 1: bool(block.get("super_over")) for i, block in enumerate(innings_meta)}
    inn_declared = {i + 1: bool(block.get("declared")) for i, block in enumerate(innings_meta)}
    inn_target = {
        i + 1: (block.get("target") or {}).get("runs") for i, block in enumerate(innings_meta)
    }

    d_rows, bat, bowl, field = (
        [],
        OrderedDict(),
        OrderedDict(),
        defaultdict(lambda: {"catches": 0, "run_outs": 0, "stumpings": 0}),
    )
    inn_acc: dict[int, dict] = defaultdict(
        lambda: {
            "runs": 0,
            "wk": 0,
            "legal": 0,
            "byes": 0,
            "legbyes": 0,
            "wides": 0,
            "noballs": 0,
            "pen": 0,
            "extras": 0,
        }
    )
    over_runs: dict[tuple, int] = defaultdict(int)
    over_legal: dict[tuple, int] = defaultdict(int)
    order: dict[int, list] = defaultdict(list)
    legal_seq: dict[int, int] = defaultdict(int)

    flat = [
        dl
        for blk in doc.get("innings") or []
        if isinstance(blk, dict)
        for ov in blk.get("overs") or []
        for dl in ov.get("deliveries") or []
    ]
    if not (len(flat) == len(parsed["deliveries"]) == len(deliveries)):
        raise ValueError(f"delivery count mismatch in match {mid}")
    for el, d in zip(flat, deliveries, strict=True):
        n = d["innings_number"]
        batting_team = inn_team.get(n)
        bowling_team = next((t for t in teams if t != batting_team), None)
        legal = not d["is_wide"] and not d["is_no_ball"]
        if legal:
            legal_seq[n] += 1
        batter, nons, bowler = d["batter_id"], d["non_striker_id"], d["bowler_id"]
        out_name = d["dismissed_player_id"]
        wk = el.get("wickets") or []
        nb_runs = int((el.get("extras") or {}).get("noballs", 0))
        d_rows.append(
            {
                "delivery_id": d["delivery_id"],
                "match_id": mid,
                "innings_id": d["innings_id"],
                "innings_number": n,
                "over_number": d["over_number"],
                "ball_number": d["ball_number"],
                "delivery_sequence": d["delivery_sequence"],
                "legal_delivery_number": legal_seq[n] if legal else None,
                "legal_ball_number": legal_seq[n] if legal else None,
                "batting_team_id": team_ids.get(batting_team),
                "bowling_team_id": team_ids.get(bowling_team),
                "batter_id": pid(batter),
                "non_striker_id": pid(nons),
                "bowler_id": pid(bowler),
                "batter_runs": d["batter_runs"],
                "extra_runs": d["extra_runs"],
                "total_runs": d["total_runs"],
                "extras_type": d["extras_type"],
                "is_wide": d["is_wide"],
                "is_no_ball": d["is_no_ball"],
                "is_bye": d["is_bye"],
                "is_leg_bye": d["is_leg_bye"],
                "is_penalty": d["is_penalty"],
                "is_legal_ball": legal,
                "is_wicket": d["is_wicket"],
                "dismissal_type": d["dismissal_type"],
                "dismissed_player_id": pid(out_name),
                "fielder_id": pid(d["fielder_id"]),
                "batter_name": batter,
                "non_striker_name": nons,
                "bowler_name": bowler,
                "dismissed_player_name": out_name,
                "fielder_name": d["fielder_id"],
                "delivery_source": "Cricsheet",
                "source_url": f"cricsheet://{mid}.json",
            }
        )
        a = inn_acc[n]
        a["runs"] += d["total_runs"]
        a["legal"] += int(legal)
        a["extras"] += d["extra_runs"]
        a["byes"] += d["extra_runs"] if d["is_bye"] else 0
        a["legbyes"] += d["extra_runs"] if d["is_leg_bye"] else 0
        a["wides"] += d["extra_runs"] if d["is_wide"] else 0
        a["noballs"] += nb_runs if d["is_no_ball"] else 0
        a["pen"] += d["extra_runs"] if d["is_penalty"] else 0
        # ----- batting
        for who in (batter, nons):
            if who and who not in order[n]:
                order[n].append(who)
        key = (n, batter)
        b = bat.setdefault(
            key,
            {
                "runs": 0,
                "balls": 0,
                "fours": 0,
                "sixes": 0,
                "out": None,
                "kind": None,
                "by": None,
                "fielder": None,
            },
        )
        b["runs"] += d["batter_runs"]
        if not d["is_wide"]:
            b["balls"] += 1
        non_boundary = bool((el.get("runs") or {}).get("non_boundary"))
        if not non_boundary and not d["is_bye"] and not d["is_leg_bye"]:
            b["fours"] += int(d["batter_runs"] == 4)
            b["sixes"] += int(d["batter_runs"] == 6)
        # ----- bowling
        bk = (n, bowler)
        w = bowl.setdefault(
            bk,
            {
                "balls": 0,
                "runs": 0,
                "wkts": 0,
                "dots": 0,
                "wides": 0,
                "nb": 0,
                "overs": defaultdict(lambda: [0, 0]),
            },
        )
        if legal:
            w["balls"] += 1
        conceded = d["batter_runs"] + (d["extra_runs"] if (d["is_wide"] or d["is_no_ball"]) else 0)
        w["runs"] += conceded
        w["wides"] += d["extra_runs"] if d["is_wide"] else 0
        w["nb"] += nb_runs if d["is_no_ball"] else 0
        w["dots"] += int(legal and d["total_runs"] == 0)
        w["overs"][d["over_number"]][0] += conceded
        w["overs"][d["over_number"]][1] += int(legal)
        # ----- wickets
        for x in wk:
            a["wk"] += 1 if x.get("kind") not in NOT_OUT_KINDS else 0
            victim = x.get("player_out")
            vb = bat.setdefault(
                (n, victim),
                {
                    "runs": 0,
                    "balls": 0,
                    "fours": 0,
                    "sixes": 0,
                    "out": None,
                    "kind": None,
                    "by": None,
                    "fielder": None,
                },
            )
            if x.get("kind") not in NOT_OUT_KINDS:
                vb["out"] = True
            vb["kind"] = x.get("kind")
            vb["by"] = bowler if _wicket_credited_to_bowler(x.get("kind")) else None
            fl = [f.get("name") for f in (x.get("fielders") or []) if f.get("name")]
            vb["fielder"] = fl[0] if fl else None
            if _wicket_credited_to_bowler(x.get("kind")):
                w["wkts"] += 1
            if x.get("kind") in ("caught", "caught and bowled"):
                for name in fl or ([bowler] if x["kind"] == "caught and bowled" else []):
                    field[(name, team_ids.get(bowling_team))]["catches"] += 1
            elif x.get("kind") == "run out":
                for name in fl:
                    field[(name, team_ids.get(bowling_team))]["run_outs"] += 1
            elif x.get("kind") == "stumped":
                for name in fl:
                    field[(name, team_ids.get(bowling_team))]["stumpings"] += 1
        # over bookkeeping for maidens
        over_runs[(n, bowler, d["over_number"])] += conceded
        over_legal[(n, bowler, d["over_number"])] += int(legal)

    # penalty runs awarded to a side are listed once per innings, outside the ball-by-ball
    for n, block in enumerate(innings_meta, start=1):
        pen = sum((block.get("penalty_runs") or {}).values())
        if pen and n in inn_acc:
            inn_acc[n]["runs"] += pen
            inn_acc[n]["extras"] += pen
            inn_acc[n]["pen"] += pen

    # ----- innings rows
    inn_rows = []
    for n in sorted(inn_acc):
        a = inn_acc[n]
        batting_team = inn_team.get(n)
        bowling_team = next((t for t in teams if t != batting_team), None)
        inn_rows.append(
            {
                "match_id": mid,
                "innings_id": f"{mid}_{n}",
                "innings_number": n,
                "innings_type": "super_over" if inn_super[n] else "standard",
                "batting_team_id": team_ids.get(batting_team),
                "bowling_team_id": team_ids.get(bowling_team),
                "total_runs": a["runs"],
                "wickets": a["wk"],
                "overs": _overs_text(a["legal"]),
                "extras": a["extras"],
                "byes": a["byes"],
                "legbyes": a["legbyes"],
                "wides": a["wides"],
                "noballs": a["noballs"],
                "penalties": a["pen"],
                "declared": inn_declared[n],
                "is_super_over": inn_super[n],
                "target": inn_target[n],
                "source_name": "Cricsheet",
                "source_url": f"cricsheet://{mid}.json",
                "_source_file": f"data/raw/competitions/cricsheet/{mid}.json",
                "legal_balls": a["legal"],
                "derived_from_deliveries": True,
                "overs_source": _overs_text(a["legal"]),
            }
        )

    # ----- batting rows (everyone who batted, plus the rest of the XI as 'did not bat')
    bat_rows = []
    for (n, name), b in bat.items():
        if name is None:
            continue
        team = team_ids.get(inn_team.get(n))
        position = order[n].index(name) + 1 if name in order[n] else None
        sr = round(100 * b["runs"] / b["balls"], 2) if b["balls"] else None
        p = pid(name)
        bat_rows.append(
            {
                "batting_scorecard_id": f"{mid}_{n}_{p}",
                "match_id": mid,
                "innings_id": f"{mid}_{n}",
                "innings_number": n,
                "player_id": p,
                "player_name": name,
                "team_id": team,
                "batting_position": position,
                "did_bat": True,
                "runs": b["runs"],
                "balls_faced": b["balls"],
                "fours": b["fours"],
                "sixes": b["sixes"],
                "strike_rate": sr,
                "is_out": bool(b["out"]),
                "dismissal_type": b["kind"] if b["out"] else None,
                "dismissal": b["kind"] if b["out"] else "not out",
                "dismissed_by": b["by"] if b["out"] else None,
                "fielder": b["fielder"] if b["out"] else None,
                "source_url": f"cricsheet://{mid}.json",
            }
        )
    batted = {(r["innings_number"], r["player_name"]) for r in bat_rows}
    for n, batting_team in inn_team.items():
        if inn_super.get(n):
            continue
        for name in (info.get("players") or {}).get(batting_team, []):
            if (n, name) in batted:
                continue
            # only list the XI once, in the first innings of their side, as a "did not bat" row
            if any(r["player_name"] == name and r["match_id"] == mid for r in bat_rows):
                continue
            p = pid(name)
            bat_rows.append(
                {
                    "batting_scorecard_id": f"{mid}_{n}_{p}",
                    "match_id": mid,
                    "innings_id": f"{mid}_{n}",
                    "innings_number": n,
                    "player_id": p,
                    "player_name": name,
                    "team_id": team_ids.get(batting_team),
                    "batting_position": None,
                    "did_bat": False,
                    "runs": None,
                    "balls_faced": None,
                    "fours": None,
                    "sixes": None,
                    "strike_rate": None,
                    "is_out": False,
                    "dismissal_type": None,
                    "dismissal": "did not bat",
                    "dismissed_by": None,
                    "fielder": None,
                    "source_url": f"cricsheet://{mid}.json",
                }
            )

    # ----- bowling rows
    bowl_rows = []
    for (n, name), w in bowl.items():
        if name is None:
            continue
        team = team_ids.get(next((t for t in teams if t != inn_team.get(n)), None))
        maidens = sum(
            1
            for (nn, bw, ov), runs in over_runs.items()
            if nn == n and bw == name and runs == 0 and over_legal[(nn, bw, ov)] == 6
        )
        p = pid(name)
        bowl_rows.append(
            {
                "bowling_scorecard_id": f"{mid}_{n}_{p}",
                "match_id": mid,
                "innings_id": f"{mid}_{n}",
                "innings_number": n,
                "player_id": p,
                "player_name": name,
                "team_id": team,
                "overs": _overs_text(w["balls"]),
                "balls_bowled": w["balls"],
                "maidens": maidens,
                "runs_conceded": w["runs"],
                "wickets": w["wkts"],
                "economy": round(6 * w["runs"] / w["balls"], 2) if w["balls"] else None,
                "dots": w["dots"],
                "wides": w["wides"],
                "no_balls": w["nb"],
                "source_url": f"cricsheet://{mid}.json",
            }
        )

    field_rows = []
    for (name, team), f in field.items():
        p = pid(name)
        field_rows.append(
            {
                "match_id": mid,
                "player_id": p,
                "player_name": name,
                "team_id": team,
                **f,
                "source_url": f"cricsheet://{mid}.json",
            }
        )

    # ----- match row
    outcome = info.get("outcome") or {}
    event = info.get("event") or {}
    winner = outcome.get("winner")
    by = outcome.get("by") or {}
    result = outcome.get("result")
    is_tie = result == "tie" or ("eliminator" in outcome) or ("bowl_out" in outcome)
    if "eliminator" in outcome:
        winner = outcome["eliminator"]
    if "bowl_out" in outcome:
        winner = outcome["bowl_out"]
    margin_type = (
        "runs"
        if "runs" in by
        else "wickets"
        if "wickets" in by
        else "innings"
        if "innings" in by
        else None
    )
    margin_value = (
        by.get("runs")
        if "runs" in by
        else by.get("wickets")
        if "wickets" in by
        else by.get("innings")
    )
    if result == "no result":
        margin_type = "no_result"
    if result == "draw":
        margin_type = "draw"
    if result == "tie":
        margin_type = "tie"
    if "innings" in by and "runs" in by:
        margin_type, margin_value = "runs", by["runs"]  # "innings and N runs"
    stage_raw = event.get("stage")
    stage = STAGE_MAP.get(
        stage_raw, "Group Stage"
    )  # Test cycles: the league matches are the "group stage"
    group = event.get("group")
    names = {t: t for t in teams}
    t1, t2 = teams[0], teams[1]
    toss = info.get("toss") or {}
    pom = (info.get("player_of_match") or [None])[0]
    balls_remaining = None
    if margin_type == "wickets" and fmt != "Test":
        last = max((n for n in inn_acc if not inn_super.get(n)), default=None)
        if last:
            balls_remaining = int((info.get("overs") or 50) * 6 - inn_acc[last]["legal"])
    method = outcome.get("method")
    venue = info.get("venue")
    tie_break = (
        "super over" if "eliminator" in outcome else "bowl-out" if "bowl_out" in outcome else None
    )
    if winner and "innings" in by and "runs" in by:
        res_text = f"{winner} won by an innings and {by['runs']} runs"
    elif winner and margin_type in ("runs", "wickets", "innings"):
        res_text = f"{winner} won by {margin_value} {margin_type}" + (
            f" ({method} method)" if method else ""
        )
    elif result == "draw":
        res_text = "Match drawn"
    elif is_tie:
        res_text = "Match tied" + (f" ({winner} won the {tie_break})" if winner else "")
    else:
        res_text = str(result or "")
    return {
        "match": {
            "match_id": mid,
            "tournament_id": tournament_id,
            "match_number": event.get("match_number"),
            "match_date": pd.to_datetime(info["dates"][0]).date(),
            "start_time": pd.NaT,
            "venue": venue,
            "city": info.get("city"),
            "team1_id": team_ids[t1],
            "team2_id": team_ids[t2],
            "team1_name": t1,
            "team2_name": t2,
            "toss_winner_id": team_ids.get(toss.get("winner")),
            "toss_decision": toss.get("decision"),
            "winner_id": team_ids.get(winner) if winner else None,
            "result_type": "RESULT" if winner or result in ("tie", "draw") else "NO RESULT",
            "result_margin": res_text,
            "player_of_match_id": pid(pom) if pom else None,
            "scorecard_url": None,
            "commentary_url": None,
            "ball_by_ball_status": "complete" if deliveries else "unavailable",
            "ball_by_ball_source": "Cricsheet",
            "scorecard_status": "complete",
            "source_url": f"cricsheet://{mid}.json",
            "winner_id_source": team_ids.get(winner) if winner else None,
            "winner_id_corrected": False,
            "toss_winner_id_source": team_ids.get(toss.get("winner")),
            "toss_winner_id_corrected": False,
            "margin_type": margin_type,
            "margin_value": float(margin_value) if margin_value is not None else None,
            "balls_remaining": float(balls_remaining) if balls_remaining is not None else None,
            "is_tie": bool(is_tie),
            "tie_break_method": tie_break,
            "tie_break_winner_name": winner if is_tie and winner else None,
            "is_dls": method == "D/L",
            "is_walkover": False,
            "result_winner_name": winner,
            "winner_source": "result" if winner else None,
            "has_winner": bool(winner) and not (is_tie and not winner),
            "match_type": stage_raw
            or (f"{event.get('match_number')}th match" if event.get("match_number") else None),
            "source_title": stage_raw,
            "group_name": (
                event.get("name") if fmt == "Test" else (f"Group {group}" if group else None)
            ),
            "match_stage_source": stage,
            "stage": stage,
            "is_knockout": stage in KNOCKOUT,
            "venue_clean": venue,
            "venue_name_canonical": venue,
            "venue_key": norm(venue) if venue else None,
        },
        "innings": inn_rows,
        "deliveries": d_rows,
        "batting": bat_rows,
        "bowling": bowl_rows,
        "fielding": field_rows,
        "xi": {t: [(n, pid(n)) for n in (info.get("players") or {}).get(t, [])] for t in teams},
        "pom": (pid(pom), pom) if pom else None,
    }


# --------------------------------------------------------------------------- competition
def _accumulate(tables, squads_map, awards, ident, m, tid) -> None:
    tables["matches"].append(m["match"])
    for k in ("innings", "deliveries", "batting", "bowling", "fielding"):
        tables[k].extend(m[k])
    for team, xi in m["xi"].items():
        team_id = team if str(team).startswith(("espn_", "cricsheet_team_")) else ident.team(team)
        for name, p in xi:
            rec = squads_map.setdefault(
                (tid, team_id, p),
                {
                    "name": name,
                    "team": ident.team_name(team_id) or team,
                    "date": m["match"]["match_date"],
                },
            )
            rec["date"] = min(rec["date"], m["match"]["match_date"])
    if m["pom"] and m["pom"][0]:
        awards.append(
            {
                "match_id": m["match"]["match_id"],
                "award_type": "PLAYER_OF_MATCH",
                "player_id": m["pom"][0],
                "tournament_id": tid,
                "award_scope": "match",
                "team_id": None,
            }
        )


def build_competition(code: str, batch: str | None = None) -> dict[str, Any]:
    from src.competitions import espn_silver as ES

    reg = load_registry()[code]
    fmt = reg["format"]
    ident = Identities()
    now = datetime.now(UTC)
    batch = batch or now.strftime("%Y%m%dT%H%M%SZ")
    editions = {
        e["year"]: e for e in reg["editions"] if e.get("source") in ("cricsheet", "espncricinfo")
    }
    docs = []
    for f in sorted((RAW / code).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["_match_id"] = f.stem
        docs.append(d)
    docs.sort(key=lambda d: (d["info"]["dates"][0], d["_match_id"]))

    # ESPNcricinfo supplement (schedule incl. abandoned matches, scorecards, squads, points tables)
    espn: dict[str, dict] = {}
    for year, e in editions.items():
        tid = f"{code}_M_{year}"
        ed = ES.load_edition(tid) if e.get("espn_series") else None
        if ed:
            espn[tid] = ed
            for mid, card in ed["cards"].items():
                ident.match_roster[mid] = ES.card_roster(card)
                for pl_ in card.get("players", []):
                    ident.extra_players.setdefault(
                        pl_["player_id"],
                        {
                            "player_id": pl_["player_id"],
                            "full_name": pl_.get("player_name"),
                            "batting_name": pl_.get("batting_name") or pl_.get("player_name"),
                            "source_player_id": pl_.get("source_player_id"),
                            "batting_style": None,
                            "bowling_style": None,
                            "date_of_birth": None,
                            "identity_source": "espncricinfo",
                            "cricsheet_names": None,
                            "cricsheet_ids": None,
                        },
                    )
            for sq in ed["squads"]:
                for p in sq["players"]:
                    ident.extra_players[p["player_id"]] = {
                        "player_id": p["player_id"],
                        "full_name": p["full_name"],
                        "batting_name": p["batting_name"],
                        "source_player_id": p["source_player_id"],
                        "batting_style": p["batting_style"],
                        "bowling_style": p["bowling_style"],
                        "date_of_birth": p["date_of_birth"],
                        "identity_source": "espncricinfo",
                        "cricsheet_names": None,
                        "cricsheet_ids": None,
                    }

    tables: dict[str, list] = defaultdict(list)
    squads_map: dict[tuple, dict] = {}
    awards: list[dict] = []
    in_cricsheet: set[str] = set()
    tid_of = {mid: tid for tid, ed in espn.items() for mid in ed["schedule"]}
    for doc in docs:
        tid = tid_of.get(str(doc["_match_id"]))
        if tid is None:
            year = int(doc["info"]["dates"][0][:4])
            if year not in editions or code == "WTC" and espn:
                continue  # a Test that is not in any championship cycle
            tid = f"{code}_M_{year}"
        m = build_match(doc, ident, tid, editions[int(tid.rsplit('_', 1)[1])].get("format", fmt))
        in_cricsheet.add(m["match"]["match_id"])
        rec = (espn.get(tid) or {}).get("schedule", {}).get(m["match"]["match_id"])
        if rec:  # ESPNcricinfo's own match numbering and title
            m["match"]["match_number"] = rec.get("match_number") or m["match"]["match_number"]
            m["match"]["match_type"] = rec.get("match_type") or m["match"]["match_type"]
        _accumulate(tables, squads_map, awards, ident, m, tid)
    ident.current_mid = None

    for tid, ed in espn.items():
        group_of = {
            mid: row["group_name"]
            for row in ed["standings"]
            for mid in (row.get("group_match_ids") or [])
        }
        for row in tables["matches"]:
            if row["tournament_id"] == tid and row["match_id"] in group_of:
                row["group_name"] = group_of[row["match_id"]]
        for mid, rec in sorted(ed["schedule"].items(), key=lambda kv: (kv[1]["match_date"], kv[0])):
            if mid in in_cricsheet or str(rec.get("result_type")).upper() not in (
                "RESULT",
                "ABANDONED",
                "NO RESULT",
                "DRAW",
                "TIE",
            ):
                continue
            m = ES.espn_match(rec, ed["cards"].get(mid), ident, tid, group_of)
            for k in ("batting", "bowling", "fielding"):
                ident.used_players.update(r["player_id"] for r in m[k])
            _accumulate(tables, squads_map, awards, ident, m, tid)

    matches = pd.DataFrame(tables["matches"])
    # tournaments
    trows = []
    for year, e in editions.items():
        tid = f"{code}_M_{year}"
        mm = matches[matches["tournament_id"] == tid].sort_values(["match_date", "match_id"])
        if mm.empty:
            continue
        final = mm[(mm["stage"] == "Final") & mm["has_winner"]]
        winner = runner = None
        if len(final):
            fr = final.iloc[-1]
            winner = fr["result_winner_name"] or ident.team_name(fr["winner_id"])
            runner = fr["team2_name"] if winner == fr["team1_name"] else fr["team1_name"]
        elif e.get("joint_winners"):
            winner = " & ".join(e["joint_winners"]) + " (joint)"
        name = (
            f"{reg['name']} {year}"
            if code in ("CT", "ASIA")
            else f"ICC World Test Championship {e['label']}"
            + (" (in progress)" if e.get("in_progress") else "")
        )
        url = (
            f"https://www.espncricinfo.com/series/{e['espn_series']}"
            if e.get("espn_series")
            else "https://cricsheet.org/downloads/"
        )
        trows.append(
            {
                "tournament_id": tid,
                "tournament_name": name,
                "year": year,
                "format": e.get("format", fmt),
                "gender": "Men",
                "host_country": e["host_country"],
                "start_date": mm["match_date"].min(),
                "end_date": mm["match_date"].max(),
                "winner": winner,
                "runner_up": runner,
                "number_of_teams": len(set(mm["team1_name"]) | set(mm["team2_name"])),
                "number_of_matches": len(mm),
                "source_url": url,
                "collection_status": "complete",
                "completion_status": "in_progress" if e.get("in_progress") else "completed",
                "_batch_id": batch,
                "_ingested_at": now.isoformat(),
            }
        )
    tournaments = pd.DataFrame(trows)

    # official squads where ESPNcricinfo has them; otherwise the players named in a playing XI
    srows = ES.squad_rows
    squad_list: list[dict] = []
    official: set[tuple] = set()
    for tid, ed in espn.items():
        rows = srows(tid, ed["squads"], batch)
        squad_list.extend(rows)
        official.update((r["tournament_id"], r["team_id"]) for r in rows)
        for r in rows:
            ident.used_players.add(r["player_id"])

    # players / teams actually used
    players_old = pd.read_parquet(SILVER / "players" / "part-0.parquet")
    used = ident.used_players
    prow: dict[str, dict] = {}
    for r in players_old[players_old["player_id"].isin(used)].to_dict("records"):
        prow[r["player_id"]] = r
    for pid_, r in ident.extra_players.items():
        if pid_ in used and pid_ not in prow:
            prow[pid_] = r
    for pid_, r in ident.new_players.items():
        if pid_ in used and pid_ not in prow:
            prow[pid_] = r
    pl = pd.DataFrame(list(prow.values()))
    teams_old = pd.read_parquet(SILVER / "teams" / "part-0.parquet")
    used_teams = set(matches["team1_id"]) | set(matches["team2_id"])
    teams = pd.concat(
        [
            teams_old[teams_old["team_id"].isin(used_teams)],
            pd.DataFrame(list(ident.new_teams.values())),
        ],
        ignore_index=True,
    ).drop_duplicates("team_id")

    for (tid, team_id, p), rec in squads_map.items():
        if (tid, team_id) in official:
            continue
        r = prow.get(p)
        squad_list.append(
            {
                "tournament_id": tid,
                "team_id": team_id,
                "team_name": rec["team"],
                "announced_at": None,
                "player_id": p,
                "source_player_id": None if r is None else r.get("source_player_id"),
                "full_name": None if r is None else r["full_name"],
                "batting_name": rec["name"],
                "role_code": None,
                "is_captain": False,
                "is_wicketkeeper": False,
                "playing_roles": None,
                "batting_style": None if r is None else r.get("batting_style"),
                "bowling_style": None if r is None else r.get("bowling_style"),
                "date_of_birth": None if r is None else r.get("date_of_birth"),
                "is_overseas": None,
                "is_withdrawn": False,
                "note": "named in a playing XI (no squad list is published for this edition)",
                "collected_at": now.isoformat(),
                "_source_file": "data/raw/competitions",
                "_batch_id": batch,
                "_ingested_at": now.isoformat(),
                "source": "playing_xi",
            }
        )
    squads = pd.DataFrame(squad_list)

    standings_list: list[dict] = []
    for tid, ed in espn.items():
        standings_list.extend(ES.standings_rows(tid, ed["standings"], matches, batch))
    cols = [
        "tournament_id",
        "group_name",
        "team_id",
        "team_name",
        "short_name",
        "source_team_id",
        "position",
        "matches_played",
        "wins",
        "losses",
        "ties",
        "no_results",
        "points",
        "net_run_rate",
        "runs_for",
        "runs_against",
        "qualified",
        "collected_at",
        "_source_file",
        "_batch_id",
        "_ingested_at",
    ]
    standings = pd.DataFrame(standings_list, columns=cols)

    awards_df = pd.DataFrame(awards)
    awards_df = _add_tournament_awards(awards_df, ident, code, tables)

    out = {
        "tournaments": tournaments,
        "teams": teams,
        "matches": matches,
        "innings": pd.DataFrame(tables["innings"]),
        "deliveries": pd.DataFrame(tables["deliveries"]),
        "players": pl,
        "batting": pd.DataFrame(tables["batting"]),
        "bowling": pd.DataFrame(tables["bowling"]),
        "fielding": pd.DataFrame(tables["fielding"]),
        "squads": squads,
        "standings": standings,
        "awards": awards_df,
    }
    root = OUT / code.lower()
    for name, df in out.items():
        df = _typed(name, df)
        d = root / "data" / "silver" / name
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "part-0.parquet", index=False)
    return {"root": str(root), "rows": {k: int(len(v)) for k, v in out.items()}}


def _full_name(ident: Identities, pid: str) -> str | None:
    extra = (ident.extra_players.get(pid) or {}).get("full_name")
    if extra:
        return str(extra)
    n = ident.display_name(pid)
    return None if n == pid else n


def _add_tournament_awards(
    awards: pd.DataFrame, ident: Identities, code: str, tables: dict
) -> pd.DataFrame:
    path = ROOT / "config" / "competition_awards.csv"
    if not path.exists():
        return awards
    rows = []
    perf = pd.DataFrame(tables["batting"] + tables["bowling"] + tables["fielding"])
    names: dict[str, str] = {}
    for key in ("batting", "bowling", "fielding"):
        for r in tables[key]:
            names.setdefault(r["player_id"], r.get("player_name") or (ident.extra_players.get(r["player_id"]) or {}).get("full_name") or ident.display_name(r["player_id"]))
    for r in pd.read_csv(path, dtype=str).itertuples():
        if not str(r.tournament_id).startswith(f"{code}_"):
            continue
        team_id = ident.team(r.team_name) if isinstance(r.team_name, str) else None
        match_ids = {
            m["match_id"] for m in tables["matches"] if m["tournament_id"] == r.tournament_id
        }
        pool = (
            perf[perf["match_id"].isin(match_ids) & (perf["team_id"] == team_id)]
            if len(perf)
            else perf
        )
        local: dict[str, str] = {}  # the name a player carries in THIS edition (e.g. Yousuf Youhana -> Mohammad Yousuf)
        for key in ("batting", "bowling", "fielding"):
            for row in tables[key]:
                if row["match_id"] in match_ids and row.get("player_name"):
                    local.setdefault(row["player_id"], row["player_name"])
        roster = [
            RosterPlayer(pid, _full_name(ident, pid) or local.get(pid) or nm or "", local.get(pid) or nm or "", team_id)
            for pid, nm in names.items()
            if pid in set(pool["player_id"])
        ]
        pid, _ = resolve_name(r.player_name, roster)
        if pid is None:
            raise ValueError(
                f"cannot match award player {r.player_name!r} ({r.tournament_id}) to a player in the data"
            )
        ident.used_players.add(pid)
        rows.append(
            {
                "match_id": None,
                "award_type": str(r.award_type).upper(),
                "player_id": pid,
                "tournament_id": r.tournament_id,
                "award_scope": "tournament",
                "team_id": team_id,
            }
        )
    return pd.concat([awards, pd.DataFrame(rows)], ignore_index=True) if rows else awards


INT_COLS = {
    "matches": ["match_number"],
    "innings": [
        "innings_number",
        "total_runs",
        "wickets",
        "extras",
        "byes",
        "legbyes",
        "wides",
        "noballs",
        "penalties",
        "target",
        "legal_balls",
    ],
    "deliveries": [
        "innings_number",
        "over_number",
        "ball_number",
        "delivery_sequence",
        "legal_delivery_number",
        "legal_ball_number",
        "batter_runs",
        "extra_runs",
        "total_runs",
    ],
    "batting": ["innings_number", "batting_position", "runs", "balls_faced", "fours", "sixes"],
    "bowling": [
        "innings_number",
        "balls_bowled",
        "maidens",
        "runs_conceded",
        "wickets",
        "dots",
        "wides",
        "no_balls",
    ],
    "fielding": ["catches", "run_outs", "stumpings"],
    "tournaments": ["year", "number_of_teams", "number_of_matches"],
    "standings": ["position", "matches_played", "wins", "losses", "ties", "no_results"],
}
BOOL_COLS = {
    "innings": ["declared", "is_super_over"],
    "deliveries": [
        "is_wide",
        "is_no_ball",
        "is_bye",
        "is_leg_bye",
        "is_penalty",
        "is_legal_ball",
        "is_wicket",
    ],
    "squads": ["is_captain", "is_wicketkeeper", "is_withdrawn"],
    "standings": ["qualified"],
}


def _typed(name: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("date_of_birth", "announced_at"):
        if c in df:
            df[c] = df[c].map(lambda v: None if v is None or v != v else str(v)[:10])
    for c in INT_COLS.get(name, []):
        if c in df:
            df[c] = pd.array(df[c], dtype="Int64")
    for c in BOOL_COLS.get(name, []):
        if c in df:
            df[c] = df[c].astype("boolean")
    return df


if __name__ == "__main__":
    import sys

    for code in sys.argv[1:] or ["CT", "WTC"]:
        print(code, build_competition(code))
