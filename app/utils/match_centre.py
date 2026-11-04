# ruff: noqa: E501
"""Data for the Match Centre (scoreboard, scorecards, ball-by-ball, partnerships, charts).

Everything is read from the gold layer; nothing is estimated. Where a value is not stored for a match (no ball-by-ball,
abandoned match, ...) the field is None / the list is empty and the UI hides it instead of showing a zero.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from app.utils.database import run
from app.utils.flags import canonical, flag_code
from app.utils.theme import AMBER, BLUE, PINK, TEAL

LIMITED_OVERS = {"ODI": 50, "T20": 20}
NOT_BOWLER_WICKETS = {"run out", "retired hurt", "retired out", "obstructing the field"}


# ---------------------------------------------------------------- helpers
def _py(v: Any) -> Any:
    """numpy / pandas scalars -> JSON-safe python values (NaN -> None)."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item") and not isinstance(v, str | bytes):
        try:
            return _py(v.item())
        except (ValueError, AttributeError):
            return str(v)
    if v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return str(v.date())
    return v


def _num(v: Any) -> float | int | None:
    v = _py(v)
    return v if isinstance(v, int | float) and not isinstance(v, bool) else None


def cricket_overs(legal_balls: int) -> str:
    """Overs in cricket notation: 107 balls -> '17.5'."""
    return f"{legal_balls // 6}.{legal_balls % 6}"


def _overs_from_float(o: Any) -> str | None:
    o = _num(o)
    return None if o is None else (str(int(o)) if o == int(o) else str(o))


def _team(name: str | None) -> dict:
    return {"name": name, "flag": flag_code(name), "short": _initials(name)}


def _initials(name: str | None) -> str:
    if not name:
        return "?"
    parts = [p for p in str(name).replace("-", " ").split() if p and p[0].isalpha()]
    if len(parts) == 1:
        return parts[0][:3].upper()
    return "".join(p[0] for p in parts)[:3].upper()


def _players(ids: list[str]) -> dict[str, str]:
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    df = run(f"select player_id, full_name from gold.dim_players where player_id in ({ph})", tuple(ids))
    return dict(zip(df["player_id"], df["full_name"], strict=True))


# ---------------------------------------------------------------- loaders
def header(mid: str) -> dict:
    df = run(
        "select m.*, t1.team_name as t1n, t2.team_name as t2n, w.team_name as wn, tw.team_name as ton, "
        "v.venue_name as venue, v.city as venue_city, pm.full_name as pom "
        "from gold.fact_matches m join gold.dim_teams t1 on t1.team_id = m.team1_id "
        "join gold.dim_teams t2 on t2.team_id = m.team2_id "
        "left join gold.dim_teams w on w.team_id = m.winner_id "
        "left join gold.dim_teams tw on tw.team_id = m.toss_winner_id "
        "left join gold.dim_venues v on v.venue_id = m.venue_id "
        "left join gold.dim_players pm on pm.player_id = m.player_of_match_id where m.match_id = ?",
        (mid,),
    )
    return df.iloc[0].to_dict() if len(df) else {}


def deliveries(mid: str) -> pd.DataFrame:
    return run(
        "select innings_number as inn, is_super_over as so, over_number as ov, delivery_sequence as seq, batter_id, "
        "non_striker_id, bowler_id, batter_runs as br, extra_runs as xr, total_runs as tr, is_wide as wd, is_no_ball as nb, "
        "is_bye as bye, is_leg_bye as lb, is_penalty as pen, is_legal_ball as legal, is_four as four, is_six as six, "
        "is_wicket as wkt, dismissal_type as dtype, dismissed_player_id as out_id, fielder_id, cumulative_runs as cum, "
        "cumulative_wickets as cw from gold.fact_deliveries where match_id = ? order by innings_number, delivery_sequence",
        (mid,),
    )


def _result_text(h: dict) -> tuple[str, str]:
    """(result headline, kind) kind in won / tie / draw / no_result / abandoned."""
    w = h.get("wn")
    mt = h.get("margin_type")
    rt = str(h.get("result_type") or "")
    if mt == "abandoned" or rt == "ABANDONED":
        return "MATCH ABANDONED", "abandoned"
    if mt == "no_result" or rt == "NO RESULT":
        return "NO RESULT", "no_result"
    if _py(h.get("is_tie")) or mt == "tie":
        tb = h.get("tie_break_method")
        txt = "MATCH TIED"
        if w:
            txt += f" · {w.upper()} WON" + (f" ({str(tb).upper()})" if tb else "")
        return txt, "tie"
    if w:
        dls = " (DLS)" if _py(h.get("is_dls")) else ""
        if mt in ("runs", "wickets") and _num(h.get("margin_value")) is not None:
            n = int(h["margin_value"])
            unit = mt[:-1] if n == 1 else mt
            return f"{w.upper()} WON BY {n} {unit.upper()}{dls}", "won"
        if mt == "walkover":
            return f"{w.upper()} WON BY WALKOVER", "won"
        extra = h.get("result_margin")
        return (f"{w.upper()} WON" + (f" · {str(extra).upper()}" if extra else "") + dls), "won"
    if mt == "draw" or "draw" in rt.lower():
        return "MATCH DRAWN", "draw"
    return (str(mt or rt or "RESULT NOT RECORDED").upper().replace("_", " "), "no_result")


def _innings_rows(mid: str, h: dict) -> list[dict]:
    inn = run(
        "select innings_number n, batting_team bat, bowling_team bowl, total_runs runs, wickets, overs, legal_balls lb, run_rate rr, "
        "extras, wides, noballs, byes, legbyes, penalties, target, fours, sixes, runs_powerplay pp_runs, "
        "wickets_powerplay pp_w, dot_balls dots, is_super_over so, is_chase chase, has_ball_by_ball bbb "
        "from gold.fact_innings where match_id = ? order by innings_number",
        (mid,),
    )
    return [{k: _py(v) for k, v in r.items()} for r in inn.to_dict("records")]


def _dismissal_texts(d: pd.DataFrame, names: dict) -> dict[tuple[int, str], str]:
    out: dict[tuple[int, str], str] = {}
    w = d[d["wkt"] & d["out_id"].notna()]
    for r in w.itertuples():
        t = str(r.dtype or "").lower()
        b = names.get(r.bowler_id, "")
        f = names.get(r.fielder_id, "") if isinstance(r.fielder_id, str) else ""
        if t == "bowled":
            s = f"b {b}"
        elif t == "lbw":
            s = f"lbw b {b}"
        elif t == "caught":
            s = f"c {f} b {b}" if f and f != b else f"c & b {b}"
        elif t == "caught and bowled":
            s = f"c & b {b}"
        elif t == "stumped":
            s = f"st {f} b {b}" if f else f"st b {b}"
        elif t == "run out":
            s = f"run out ({f})" if f else "run out"
        elif t == "hit wicket":
            s = f"hit wicket b {b}"
        else:
            s = t or "out"
        out[(int(r.inn), r.out_id)] = s
    return out


def _bowling_from_deliveries(d: pd.DataFrame, names: dict) -> dict[int, list[dict]]:
    """Per-innings bowling figures from the ball-by-ball (used for Tests, where the stored line sums both innings)."""
    out: dict[int, list[dict]] = {}
    for inn, g in d[~d["so"]].groupby("inn"):
        rows = []
        for bid, bg in g.groupby("bowler_id", sort=False):
            legal = int(bg["legal"].sum())
            # runs charged to the bowler: bat runs + wides + no-balls (not byes / leg byes / penalties)
            charged = int((bg["br"] + bg["xr"].where(bg["wd"] | bg["nb"], 0)).sum())
            wk = int((bg["wkt"] & ~bg["dtype"].fillna("").isin(NOT_BOWLER_WICKETS)).sum())
            om = bg.assign(c=bg["br"] + bg["xr"].where(bg["wd"] | bg["nb"], 0)).groupby("ov")
            maidens = int(((om["legal"].sum() == 6) & (om["c"].sum() == 0)).sum())
            rows.append(
                {
                    "bowler": names.get(bid, bid),
                    "overs": cricket_overs(legal),
                    "m": maidens,
                    "runs": charged,
                    "w": wk,
                    "econ": round(charged / (legal / 6), 2) if legal else None,
                    "dots": int(bg["legal"].mul(bg["tr"].eq(0)).sum()),
                }
            )
        out[int(inn)] = rows
    return out


def _chips(d: pd.DataFrame, names: dict) -> list[dict]:
    """Per innings: overs with their deliveries as compact chips."""
    out = []
    for inn, g in d[~d["so"]].groupby("inn"):
        overs = []
        legal_total = 0
        for ov, og in g.groupby("ov", sort=True):
            balls = []
            for r in og.itertuples():
                if r.wkt:
                    txt, kind = "W", "wkt"
                elif r.pen:
                    txt, kind = f"{int(r.xr)}pen", "extra"
                elif r.wd:
                    txt, kind = (f"{int(r.tr)}wd" if r.tr > 1 else "wd"), "extra"
                elif r.nb:
                    txt, kind = (f"{int(r.br)}nb" if r.br else "nb"), "extra"
                elif r.bye:
                    txt, kind = f"{int(r.xr)}b", "extra"
                elif r.lb:
                    txt, kind = f"{int(r.xr)}lb", "extra"
                elif r.six:
                    txt, kind = "6", "six"
                elif r.four:
                    txt, kind = "4", "four"
                elif r.tr == 0:
                    txt, kind = "0", "dot"
                else:
                    txt, kind = str(int(r.br)), "run"
                legal_total += int(r.legal)
                balls.append([txt, kind, int(r.tr)])
            bowlers = list(dict.fromkeys(names.get(b, b) for b in og["bowler_id"]))
            overs.append(
                {
                    "over": int(ov),
                    "bowler": " / ".join(bowlers),
                    "runs": int(og["tr"].sum()),
                    "wickets": int(og["wkt"].sum()),
                    "complete": int(og["legal"].sum()) >= 6,
                    "score": f"{int(og['cum'].iloc[-1])}/{int(og['cw'].iloc[-1])}",
                    "balls": balls,
                }
            )
        out.append({"innings": int(inn), "overs": overs})
    return out


def _fow(d: pd.DataFrame, names: dict) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for inn, g in d[~d["so"]].groupby("inn"):
        g = g.assign(lc=g["legal"].astype(int).cumsum())
        rows = []
        for r in g[g["wkt"] & g["out_id"].notna()].itertuples():
            rows.append(
                {
                    "wkt": int(r.cw),
                    "score": int(r.cum),
                    "over": cricket_overs(int(r.lc)),
                    "ov_f": round(int(r.lc) / 6, 2),
                    "batter": names.get(r.out_id, r.out_id),
                }
            )
        out[int(inn)] = rows
    return out


def _partnerships(d: pd.DataFrame, names: dict) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for inn, g in d[~d["so"]].groupby("inn"):
        parts: list[dict] = []
        seg = {"runs": 0, "balls": 0, "bat": {}, "wicket": 0}

        def close(unbroken: bool, seg: dict = seg, parts: list = parts) -> None:
            if not seg["bat"] and not seg["runs"]:
                return
            top = sorted(seg["bat"].items(), key=lambda kv: -kv[1]["seen"])[:2]
            parts.append(
                {
                    "wkt": seg["wicket"] + 1,
                    "runs": seg["runs"],
                    "balls": seg["balls"],
                    "unbroken": unbroken,
                    "batters": [
                        {"name": names.get(b, b), "runs": v["runs"], "balls": v["balls"]} for b, v in top
                    ],
                }
            )

        for r in g.itertuples():
            seg["runs"] += int(r.tr)
            seg["balls"] += int(r.legal)
            for pid in (r.batter_id, r.non_striker_id):
                if isinstance(pid, str):
                    seg["bat"].setdefault(pid, {"runs": 0, "balls": 0, "seen": 0})["seen"] += 1
            b = seg["bat"].setdefault(r.batter_id, {"runs": 0, "balls": 0, "seen": 0})
            b["runs"] += int(r.br)
            b["balls"] += int(not r.wd)
            if r.wkt and r.dtype not in ("retired hurt",):
                close(False)
                seg.update({"runs": 0, "balls": 0, "bat": {}, "wicket": int(r.cw)})
        close(True)
        out[int(inn)] = parts
    return out


# ---------------------------------------------------------------- payload
def payload(mid: str) -> dict | None:
    h = header(mid)
    if not h:
        return None
    fmt = h["format"]
    t1, t2 = h["t1n"], h["t2n"]
    innings = _innings_rows(mid, h)
    d = deliveries(mid)
    bbb = bool(len(d))
    names = _players(
        [*d["batter_id"], *d["bowler_id"], *d["fielder_id"].dropna(), *d["out_id"].dropna(), *d["non_striker_id"]]
        if bbb
        else []
    )
    dis = _dismissal_texts(d, names) if bbb else {}
    fows = _fow(d, names) if bbb else {}
    parts = _partnerships(d, names) if bbb else {}
    chips = _chips(d, names) if bbb else []
    test_bowl = _bowling_from_deliveries(d, names) if (bbb and fmt == "Test") else {}

    bat = run(
        "select f.team_id, t.team_name team, f.player_id pid, p.full_name batter, f.batting_innings bi, f.batting_position pos, "
        "f.runs, f.balls_faced balls, f.fours, f.sixes, f.strike_rate sr, f.is_out, f.dismissal_type dtype "
        "from gold.fact_player_performances f join gold.dim_players p using (player_id) "
        "join gold.dim_teams t on t.team_id = f.team_id where f.match_id = ? and f.did_bat "
        "order by f.batting_innings, f.batting_position",
        (mid,),
    )
    bowl = run(
        "select t.team_name team, p.full_name bowler, f.balls_bowled lb, f.maidens m, f.runs_conceded runs, f.wickets w, "
        "f.economy econ, f.dots from gold.fact_player_performances f join gold.dim_players p using (player_id) "
        "join gold.dim_teams t on t.team_id = f.team_id where f.match_id = ? and f.did_bowl "
        "order by f.wickets desc, f.runs_conceded",
        (mid,),
    )

    main = [i for i in innings if not i["so"]]
    # map each batting side's k-th innings to its batting_innings value
    by_team: dict[str, list[float]] = {}
    for team, g in bat.groupby("team"):
        by_team[team] = sorted(g["bi"].dropna().unique().tolist())
    seen: dict[str, int] = {}
    out_inn = []
    for i in innings:
        k = seen.get(i["bat"], 0)
        seen[i["bat"]] = k + 1
        rows = []
        if not i["so"]:
            vals = by_team.get(i["bat"], [])
            bi = vals[k] if k < len(vals) else None
            sub = bat[(bat["team"] == i["bat"]) & (bat["bi"] == bi)] if bi is not None else bat.iloc[0:0]
            rows = [
                {
                    "batter": r["batter"],
                    "how": (
                        dis.get((i["n"], r["pid"]))
                        or (r["dtype"] if r["is_out"] and r["dtype"] else None)
                        or ("not out" if not r["is_out"] else "out")
                    ),
                    "out": bool(r["is_out"]),
                    "runs": _num(r["runs"]),
                    "balls": _num(r["balls"]),
                    "fours": _num(r["fours"]),
                    "sixes": _num(r["sixes"]),
                    "sr": _num(r["sr"]),
                }
                for r in sub.to_dict("records")
            ]
        if fmt == "Test" and i["n"] in test_bowl:
            brows = test_bowl[i["n"]]
        elif i["so"]:
            brows = []
        else:
            sub = bowl[bowl["team"] == i["bowl"]]
            brows = [
                {
                    "bowler": r["bowler"],
                    "overs": cricket_overs(int(r["lb"])) if _num(r["lb"]) is not None else None,
                    "m": _num(r["m"]),
                    "runs": _num(r["runs"]),
                    "w": _num(r["w"]),
                    "econ": _num(r["econ"]),
                    "dots": _num(r["dots"]) if _num(r["dots"]) else None,
                }
                for r in sub.to_dict("records")
            ]
        legal = int(i["lb"] or 0)
        ov_txt = cricket_overs(legal) if legal else _overs_from_float(i["overs"])
        mo = LIMITED_OVERS.get(fmt)
        tgt = i["target"] if i["chase"] and i["target"] else None
        req = round(tgt / mo * 1, 2) if (tgt and mo and not _py(h.get("is_dls"))) else None
        out_inn.append(
            {
                "n": i["n"],
                "team": _team(i["bat"]),
                "bowling_team": i["bowl"],
                "runs": i["runs"],
                "wickets": i["wickets"],
                "overs": ov_txt,
                "run_rate": i["rr"],
                "super_over": bool(i["so"]),
                "extras": {
                    "total": i["extras"],
                    "wides": i["wides"],
                    "noballs": i["noballs"],
                    "byes": i["byes"],
                    "legbyes": i["legbyes"],
                    "penalties": i["penalties"],
                },
                "target": tgt,
                "required_rate_start": req,
                "batting": rows,
                "bowling": brows,
                "fow": fows.get(i["n"], []),
                "partnerships": parts.get(i["n"], []),
                "powerplay": {"runs": i["pp_runs"], "wickets": i["pp_w"]} if (fmt in LIMITED_OVERS and i["pp_runs"] is not None and i["bbb"]) else None,
                "fours": i["fours"],
                "sixes": i["sixes"],
            }
        )

    result, kind = _result_text(h)
    # per-team scoreboard lines
    board = []
    for tn in (t1, t2):
        board.append(
            {
                **_team(tn),
                "winner": bool(h.get("wn") and h["wn"] == tn and kind in ("won", "tie")),
                "innings": [
                    {"n": i["n"], "runs": i["runs"], "wickets": i["wickets"], "overs": i["overs"], "super_over": i["super_over"]}
                    for i in out_inn
                    if i["team"]["name"] == tn
                ],
            }
        )

    # headline statistics (only what the data supports)
    stats = []
    tot_runs = sum(i["runs"] or 0 for i in main)
    if main:
        stats.append(["Total runs", tot_runs, "both sides" if len(main) > 1 else ""])
        stats.append(["Wickets", sum(i["wickets"] or 0 for i in main), ""])
    legal_all = sum(int(i["lb"] or 0) for i in main)
    if legal_all:
        stats.append(["Overs bowled", cricket_overs(legal_all), ""])
        stats.append(["Match run rate", round(tot_runs / (legal_all / 6), 2), "runs per over"])
    fours = sum(i["fours"] or 0 for i in out_inn if not i["super_over"])
    sixes = sum(i["sixes"] or 0 for i in out_inn if not i["super_over"])
    if bbb and (fours or sixes):
        stats.append(["Boundaries", fours + sixes, f"{fours} fours · {sixes} sixes"])
    ex = sum(i["extras"]["total"] or 0 for i in out_inn if not i["super_over"])
    if main and any(i["extras"]["total"] is not None for i in out_inn):
        stats.append(["Extras", ex, ""])
    allp = [(p["runs"], p["wkt"], i["team"]["name"], p["batters"]) for i in out_inn for p in i["partnerships"]]
    if allp:
        r, wk, tm, bs = max(allp, key=lambda x: x[0])
        stats.append(["Highest partnership", r, f"{tm} · " + " & ".join(b["name"] for b in bs) if bs else tm])
    pps = [(i["team"]["name"], i["powerplay"]) for i in out_inn if i["powerplay"]]
    if pps:
        stats.append(["Powerplay", " · ".join(f"{_initials(t)} {p['runs']}/{p['wickets']}" for t, p in pps), "first 6 overs" if fmt == "T20" else "first 10 overs"])
    if len(bat):
        b = bat.sort_values(["runs", "balls"], ascending=[False, True]).iloc[0]
        stats.append(["Best batting", f"{int(b['runs'])}" + (f" ({int(b['balls'])})" if _num(b["balls"]) is not None else ""), f"{b['batter']} · {b['team']}"])
    if len(bowl):
        w = bowl.sort_values(["w", "runs"], ascending=[False, True]).iloc[0]
        stats.append(["Best bowling", f"{int(w['w'])}/{int(w['runs'])}", f"{w['bowler']} · {w['team']}"])

    toss = None
    if h.get("ton") and h.get("toss_decision"):
        toss = f"{h['ton']} won the toss and chose to {h['toss_decision']}"

    return {
        "match_id": mid,
        "tournament": h["tournament_name"],
        "format": fmt,
        "year": _num(h["year"]),
        "stage": h.get("stage"),
        "group": h.get("group_name"),
        "match_number": _num(h.get("match_number")),
        "date": _py(h["match_date"]),
        "venue": h.get("venue"),
        "city": None if (h.get("venue_city") and str(h.get("venue") or "").endswith(str(h["venue_city"]))) else h.get("venue_city"),
        "status": "Completed" if _py(h.get("is_completed")) else (str(h.get("result_type") or "Scheduled").title()),
        "result": result,
        "result_kind": kind,
        "toss": toss,
        "player_of_match": h.get("pom"),
        "teams": board,
        "innings": out_inn,
        "stats": [[a, _py(b), c] for a, b, c in stats],
        "chips": chips,
        "has_ball_by_ball": bbb,
        "gap_reason": None if bbb else h.get("ball_by_ball_gap_reason"),
        "source_url": h.get("source_url"),
        "known_team": [canonical(t1), canonical(t2)],
    }


# ---------------------------------------------------------------- charts
_INN_COLORS = [TEAL, AMBER, BLUE, PINK, "#9b8cff", "#7ee081"]


def _color_map(pl: dict) -> dict[int, str]:
    """One colour per team (so a Test's two innings of a side look alike), dashed for the later innings."""
    team_color: dict[str, str] = {}
    cm = {}
    for i in pl["innings"]:
        c = team_color.setdefault(i["team"]["name"], _INN_COLORS[len(team_color) % len(_INN_COLORS)])
        cm[i["n"]] = c
    return cm


def charts(mid: str, pl: dict) -> dict[str, go.Figure]:
    """Plotly figures (the dashboard theme is applied by the template). Only what the data supports."""
    d = deliveries(mid)
    d = d[~d["so"]] if len(d) else d
    if not len(d):
        return {}
    names = _players([*d["batter_id"], *d["out_id"].dropna()])
    cmap = _color_map(pl)
    inn_info = {i["n"]: i for i in pl["innings"]}
    figs: dict[str, go.Figure] = {}

    worm, rr, ovr, wkt = go.Figure(), go.Figure(), go.Figure(), go.Figure()
    for inn, g in d.groupby("inn"):
        info = inn_info[int(inn)]
        label = f"{info['team']['name']}" + (f" inns {sum(1 for x in pl['innings'] if x['team']['name'] == info['team']['name'] and x['n'] <= info['n'])}" if pl["format"] == "Test" else "")
        g = g.assign(lc=g["legal"].astype(int).cumsum())
        per_over = g.groupby("ov").agg(runs=("tr", "sum"), wk=("wkt", "sum"), cum=("cum", "max"), lc=("lc", "max"))
        x = [0, *(per_over["lc"] / 6).round(2).tolist()]
        y = [0, *per_over["cum"].tolist()]
        col = cmap[int(inn)]
        dash = "dot" if (pl["format"] == "Test" and int(inn) > 2) else "solid"
        worm.add_trace(go.Scatter(x=x, y=y, mode="lines", name=label, line=dict(color=col, width=3, dash=dash), hovertemplate="%{y} runs after %{x} overs<extra>" + label + "</extra>"))
        w = g[g["wkt"] & g["out_id"].notna()]
        if len(w):
            worm.add_trace(go.Scatter(x=(w["lc"] / 6).round(2), y=w["cum"], mode="markers", name=f"{label} wickets", showlegend=False,
                                      marker=dict(color="#ff4d6d", size=9, line=dict(color="white", width=1)),
                                      text=[f"{names.get(o, o)} out ({c}/{k})" for o, c, k in zip(w["out_id"], w["cum"], w["cw"], strict=True)],
                                      hovertemplate="%{text}<extra></extra>"))
        rate = [r / max(o, 0.1667) for r, o in zip(y[1:], x[1:], strict=True)]
        rr.add_trace(go.Scatter(x=x[1:], y=[round(v, 2) for v in rate], mode="lines", name=label, line=dict(color=col, width=3, dash=dash), hovertemplate="%{y:.2f} runs/over at %{x} overs<extra>" + label + "</extra>"))
        ovr.add_trace(go.Bar(x=per_over.index, y=per_over["runs"], name=label, marker_color=col, hovertemplate="Over %{x}: %{y} runs<extra>" + label + "</extra>"))
        wb = per_over[per_over["wk"] > 0]
        if len(wb):
            wkt.add_trace(go.Bar(x=wb.index, y=wb["wk"], name=label, marker_color=col, hovertemplate="Over %{x}: %{y} wicket(s)<extra>" + label + "</extra>"))
    worm.update_layout(title="Worm: cumulative runs", xaxis_title="Overs", yaxis_title="Runs", height=380, hovermode="x unified", legend=dict(orientation="h", y=-0.2))
    rr.update_layout(title="Run rate progression (cumulative)", xaxis_title="Overs", yaxis_title="Runs per over", height=380, hovermode="x unified", legend=dict(orientation="h", y=-0.2))
    ovr.update_layout(title="Runs in each over", xaxis_title="Over", yaxis_title="Runs", barmode="group", height=380, legend=dict(orientation="h", y=-0.2))
    wkt.update_layout(title="Wickets by over", xaxis_title="Over", yaxis_title="Wickets", barmode="stack", height=380, yaxis=dict(dtick=1), legend=dict(orientation="h", y=-0.2))
    figs["Worm"] = worm
    figs["Run rate"] = rr
    figs["Over by over"] = ovr
    if len(wkt.data):
        figs["Wickets timeline"] = wkt

    # innings comparison
    comp = go.Figure(
        go.Bar(
            x=[f"{i['team']['name']} #{k + 1}" if pl["format"] == "Test" else i["team"]["name"] for k, i in enumerate(pl["innings"])],
            y=[i["runs"] for i in pl["innings"]],
            text=[f"{i['runs']}/{i['wickets']}" for i in pl["innings"]],
            marker_color=[cmap[i["n"]] for i in pl["innings"]],
            hovertemplate="%{x}: %{text} (%{customdata} overs)<extra></extra>",
            customdata=[i["overs"] for i in pl["innings"]],
        )
    )
    comp.update_layout(title="Innings comparison", yaxis_title="Runs", height=380, showlegend=False)
    figs["Innings comparison"] = comp

    # partnerships
    pf = go.Figure()
    for i in pl["innings"]:
        ps = i["partnerships"]
        if not ps:
            continue
        pf.add_trace(go.Bar(
            x=[p["runs"] for p in ps], y=[f"{i['team']['short']} · {p['wkt']}{'*' if p['unbroken'] else ''} " + " & ".join(b['name'].split()[-1] for b in p["batters"]) for p in ps],
            orientation="h", name=i["team"]["name"], marker_color=cmap[i["n"]],
            hovertemplate="%{y}: %{x} runs<extra></extra>"))
    if len(pf.data):
        pf.update_layout(title="Partnerships (runs, * = unbroken)", height=max(340, 26 * sum(len(i["partnerships"]) for i in pl["innings"]) + 120), yaxis=dict(autorange="reversed"), xaxis_title="Runs", legend=dict(orientation="h", y=-0.12))
        figs["Partnerships"] = pf

    # fall of wickets
    ff = go.Figure()
    for i in pl["innings"]:
        if not i["fow"]:
            continue
        ff.add_trace(go.Scatter(x=[w["ov_f"] for w in i["fow"]], y=[w["score"] for w in i["fow"]], mode="markers+lines+text",
                                text=[str(w["wkt"]) for w in i["fow"]], textposition="top center", name=i["team"]["name"],
                                line=dict(color=cmap[i["n"]], width=1, dash="dot"), marker=dict(color=cmap[i["n"]], size=10),
                                customdata=[[w["batter"], w["over"]] for w in i["fow"]],
                                hovertemplate="%{customdata[0]} out at %{y} (over %{customdata[1]})<extra></extra>"))
    if len(ff.data):
        ff.update_layout(title="Fall of wickets (label = wicket number)", xaxis_title="Overs", yaxis_title="Team score", height=380, legend=dict(orientation="h", y=-0.2))
        figs["Fall of wickets"] = ff

    # chase: required vs actual run rate (limited-overs chases with a known target)
    mo = LIMITED_OVERS.get(pl["format"])
    chase = next((i for i in pl["innings"] if i["target"] and not i["super_over"]), None)
    if mo and chase:
        g = d[d["inn"] == chase["n"]].assign(lc=lambda x: x["legal"].astype(int).cumsum())
        po = g.groupby("ov").agg(cum=("cum", "max"), lc=("lc", "max"))
        po = po[po["lc"] > 0]
        left = [(mo * 6 - lc) for lc in po["lc"]]
        need = [chase["target"] - c for c in po["cum"]]
        req = [round(n / (b / 6), 2) if b > 0 and n > 0 else None for n, b in zip(need, left, strict=True)]
        act = [round(c / (lc / 6), 2) for c, lc in zip(po["cum"], po["lc"], strict=True)]
        cf = go.Figure()
        cf.add_trace(go.Scatter(x=(po["lc"] / 6).round(2), y=act, name="Actual run rate", mode="lines", line=dict(color=TEAL, width=3)))
        cf.add_trace(go.Scatter(x=(po["lc"] / 6).round(2), y=req, name="Required run rate", mode="lines", line=dict(color=AMBER, width=3, dash="dash"), connectgaps=False))
        cf.update_layout(title=f"{chase['team']['name']} chase of {chase['target']}: required vs actual run rate", xaxis_title="Overs", yaxis_title="Runs per over", height=380, hovermode="x unified", legend=dict(orientation="h", y=-0.2))
        figs["Chase"] = cf
    return figs


def match_options(tid: str) -> pd.DataFrame:
    """Matches of a tournament with everything the picker shows (flags are resolved in the browser)."""
    return run(
        "select m.match_id, m.match_date, m.stage, m.match_number, t1.team_name as team1, t2.team_name as team2, "
        "w.team_name as winner, m.margin_type, m.margin_value, m.result_type, m.is_tie, v.venue_name as venue, "
        "m.has_ball_by_ball from gold.fact_matches m join gold.dim_teams t1 on t1.team_id = m.team1_id "
        "join gold.dim_teams t2 on t2.team_id = m.team2_id left join gold.dim_teams w on w.team_id = m.winner_id "
        "left join gold.dim_venues v on v.venue_id = m.venue_id where m.tournament_id = ? "
        "order by m.match_date, m.match_id",
        (tid,),
    )


def short_result(r: dict) -> str:
    mt = r.get("margin_type")
    if mt == "abandoned" or str(r.get("result_type")) == "ABANDONED":
        return "Abandoned"
    if mt == "no_result" or str(r.get("result_type")) == "NO RESULT":
        return "No result"
    if r.get("is_tie") or mt == "tie":
        return "Tied" + (f" · {r['winner']}" if r.get("winner") else "")
    if r.get("winner"):
        if mt in ("runs", "wickets") and _num(r.get("margin_value")) is not None:
            n = int(r["margin_value"])
            return f"{r['winner']} by {n} {mt[:-1] if n == 1 else mt}"
        return f"{r['winner']} won"
    return "Drawn" if mt == "draw" else "—"
