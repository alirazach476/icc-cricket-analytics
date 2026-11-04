"""Silver layer: cleaned, typed, conformed data built from bronze (Stage 4).

Fixes the issues found in the Stage 2/3 audits, each one traceable:

* alias team ids (``winner_id`` / ``toss_winner_id`` using ids that are not the playing teams)
* tie-break winners that exist only in the result text
* result text parsed into margin type / value / DLS / walkover columns
* a real stage taxonomy (Super Eight / Ten / 12 were labelled "Group Stage"; "Other" was ambiguous)
* ball-by-ball player names resolved to ESPN ids (see ``identity.py``)
* Super Over innings totals derived from deliveries when never stored
* true legal-delivery numbering (``legal_ball_number`` counts no-balls)

Original values are preserved in ``*_source`` / ``*_original`` columns wherever a value is changed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.ingestion.bronze import read_bronze
from src.transformations.identity import NAME_COLUMNS, build_identity_map, norm

KNOCKOUT = {"Quarterfinal", "Semifinal", "Third Place", "Final"}


# --------------------------------------------------------------------------- helpers
def team_key(name: str | None) -> str:
    """Comparable team name ('U.S.A.' == 'United States of America')."""
    n = norm(name)
    return {
        "u s a": "usa",
        "united states of america": "usa",
        "united states": "usa",
        "uae": "uae",
        "united arab emirates": "uae",
    }.get(n, n)


def _bool(s: pd.Series) -> pd.Series:
    return s.map(
        lambda v: None if v is None or v != v else str(v).strip().lower() in {"true", "1", "yes"}
    ).astype("boolean")


def _int(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def _write(root: Path, entity: str, df: pd.DataFrame) -> dict[str, Any]:
    out = root / "data" / "silver" / entity
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "part-0.parquet.tmp"
    df.to_parquet(tmp, index=False)
    tmp.replace(out / "part-0.parquet")
    return {"entity": entity, "rows": int(len(df)), "columns": int(len(df.columns))}


def read_silver(root: Path, entity: str) -> pd.DataFrame:
    return pd.read_parquet(root / "data" / "silver" / entity / "part-0.parquet")


# --------------------------------------------------------------------------- teams
def resolve_team_aliases(matches: pd.DataFrame) -> pd.DataFrame:
    """Find ids used as winner / toss winner that never play (alias ids) and map them to the real team.

    An alias maps to a team only if that team is the *single* team playing in every match where the
    alias is referenced; anything ambiguous stays unmapped.
    """
    players = set(matches["team1_id"].dropna()) | set(matches["team2_id"].dropna())
    refs = pd.concat(
        [
            matches[["match_id", "team1_id", "team2_id", "winner_id"]].rename(
                columns={"winner_id": "ref"}
            ),
            matches[["match_id", "team1_id", "team2_id", "toss_winner_id"]].rename(
                columns={"toss_winner_id": "ref"}
            ),
        ]
    )
    refs = refs[refs["ref"].notna() & ~refs["ref"].isin(players)]
    rows = []
    for alias, g in refs.groupby("ref"):
        common = None
        for r in g.itertuples():
            teams = {r.team1_id, r.team2_id}
            common = teams if common is None else common & teams
        rows.append(
            {
                "alias_id": alias,
                "mapped_team_id": next(iter(common)) if common and len(common) == 1 else None,
                "evidence_matches": g["match_id"].nunique(),
            }
        )
    return pd.DataFrame(rows, columns=["alias_id", "mapped_team_id", "evidence_matches"])


def build_teams(bronze: dict[str, pd.DataFrame], aliases: pd.DataFrame) -> pd.DataFrame:
    reg = bronze["teams_registry"].drop_duplicates("team_id")
    bundle = bronze["teams"].drop_duplicates("team_id")
    t = pd.concat([reg, bundle]).drop_duplicates("team_id", keep="first")
    t = t[~t["team_id"].isin(aliases["alias_id"])]
    t = t[["team_id", "team_name", "short_name", "source_team_id"]].copy()

    def short(r):
        s = r.short_name
        if isinstance(s, str) and re.fullmatch(r"[A-Z]{2,3}", s):
            return s
        return re.sub(r"[^A-Za-z]", "", r.team_name)[:3].upper()

    t["short_name_source"] = t["short_name"]
    t["short_name"] = [short(r) for r in t.itertuples()]
    t["team_key"] = t["team_name"].map(team_key)
    return t.sort_values("team_name").reset_index(drop=True)


# --------------------------------------------------------------------------- matches
_TIED = re.compile(r"^Match tied(?: \((?P<paren>.*)\))?$", re.I)
_TIE_WINNER = re.compile(r"^(?P<who>.+?) won (?P<how>.+)$")
_WON_BY = re.compile(
    r"^(?P<who>.+?) won by (?P<n>\d+) (?P<unit>runs?|wickets?)(?: \(with (?P<balls>\d+) balls? remaining\))?",
    re.I,
)


def parse_result(text: str | None, result_type: str | None) -> dict[str, Any]:
    t = (text or "").strip()
    out: dict[str, Any] = {
        "margin_type": None,
        "margin_value": pd.NA,
        "balls_remaining": pd.NA,
        "is_tie": False,
        "tie_break_method": None,
        "tie_break_winner_name": None,
        "is_dls": False,
        "is_walkover": False,
        "result_winner_name": None,
    }
    if not t:
        return out
    out["is_dls"] = bool(re.search(r"D/L|DLS", t))
    if "walkover" in t.lower():
        out.update(
            margin_type="walkover",
            is_walkover=True,
            result_winner_name=t.split(" won")[0] if " won" in t else None,
        )
        return out
    tied = (
        _TIED.match(re.sub(r"\s*\((?:D/L|DLS) method\)", "", t).strip())
        if t.lower().startswith("match tied")
        else None
    )
    if t.lower().startswith("match tied"):
        out.update(margin_type="tie", is_tie=True)
        paren = (tied.group("paren") if tied else None) or ""
        w = _TIE_WINNER.match(paren)
        if w:
            how = w.group("how").lower()
            out["tie_break_winner_name"] = w.group("who").strip()
            out["tie_break_method"] = (
                "super over"
                if "super over" in how
                else "boundary count"
                if "boundary" in how
                else "eliminator"
                if "eliminator" in how
                else "other"
            )
        return out
    m = _WON_BY.match(t)
    if m:
        unit = m.group("unit").lower().rstrip("s")
        out.update(
            margin_type=unit + "s",
            margin_value=int(m.group("n")),
            result_winner_name=m.group("who").strip(),
        )
        if m.group("balls"):
            out["balls_remaining"] = int(m.group("balls"))
        return out
    if (result_type or "").upper() == "ABANDONED" or "abandoned" in t.lower():
        out["margin_type"] = "abandoned"
    elif "no result" in t.lower():
        out["margin_type"] = "no_result"
    return out


def _group_clusters(standings: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Group -> match assignment with a date-window cluster (round) per tournament."""
    rows = []
    for r in standings.itertuples():
        ids = json.loads(r.group_match_ids) if isinstance(r.group_match_ids, str) else []
        rows += [(r.tournament_id, r.group_name, str(mid)) for mid in ids]
    gm = pd.DataFrame(rows, columns=["tournament_id", "group_name", "match_id"]).drop_duplicates()
    if gm.empty:
        return gm.assign(round_label=None)
    x = gm.merge(matches[["match_id", "match_date"]], on="match_id")
    g = (
        x.groupby(["tournament_id", "group_name"])
        .agg(first=("match_date", "min"), last=("match_date", "max"))
        .reset_index()
    )
    teams = (
        standings.groupby(["tournament_id", "group_name"]).size().rename("n_teams").reset_index()
    )
    g = g.merge(teams, on=["tournament_id", "group_name"]).sort_values(["tournament_id", "first"])
    labels: dict[tuple[str, str], str] = {}
    for tid, sub in g.groupby("tournament_id"):
        cluster, min_last, cl = [], None, 0
        for r in sub.itertuples():
            # A group belongs to a new round when it starts after the earliest finish of the current round
            # (groups of one round overlap in time; the next round only starts once a round has finished).
            if min_last is not None and r.first > min_last:
                cl += 1
                min_last = r.last
            else:
                min_last = r.last if min_last is None else min(min_last, r.last)
            cluster.append((r.group_name, cl, r.n_teams))
        n_clusters = max(c for _, c, _ in cluster) + 1
        sizes = {}
        for _gname, c, n in cluster:
            sizes[c] = sizes.get(c, 0) + n
        for gname, c, _n in cluster:
            if n_clusters == 1:
                labels[(tid, gname)] = "Group Stage"
            elif c == 0:
                labels[(tid, gname)] = (
                    "First Round" if gname.lower().startswith("first round") else "Group Stage"
                )
            else:
                labels[(tid, gname)] = {
                    6: "Super Six",
                    8: "Super Eight",
                    10: "Super Ten",
                    12: "Super 12",
                }.get(sizes[c], "Super Stage")
    gm["round_label"] = [labels.get((r.tournament_id, r.group_name)) for r in gm.itertuples()]
    return gm


def _infer_groups(m: pd.DataFrame, stage: pd.Series, bronze: dict[str, pd.DataFrame]) -> pd.Series:
    """Group for league matches whose standings page lists no match ids (ODI 2003).

    A match is placed in a group only when exactly one stage-compatible group contains both of its
    teams ("Super" groups for Super stages, other groups otherwise). Anything ambiguous stays null.
    The result is cross-checked against the source's own win counts by the gold quality rules.
    """
    members: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for (tid, grp), g in bronze["standings"].groupby(["tournament_id", "group_name"]):
        members.setdefault(tid, []).append((grp, frozenset(g["team_id"])))
    out = pd.Series(None, index=m.index, dtype=object)
    todo = m["group_name"].isna() & ~stage.isin(KNOCKOUT) & m["team1_id"].notna()
    for idx in m.index[todo]:
        pair = {m.at[idx, "team1_id"], m.at[idx, "team2_id"]}
        super_stage = str(stage.at[idx]).lower().startswith("super")
        hits = [
            grp
            for grp, teams in members.get(m.at[idx, "tournament_id"], [])
            if pair <= teams and grp.lower().startswith("super") == super_stage
        ]
        if len(hits) == 1:
            out.at[idx] = hits[0]
    return out


def build_matches(
    bronze: dict[str, pd.DataFrame],
    aliases: pd.DataFrame,
    teams: pd.DataFrame,
    root: Path | None = None,
) -> pd.DataFrame:
    m = bronze["matches"].copy()
    keep = [
        "match_id",
        "tournament_id",
        "match_number",
        "match_stage",
        "match_date",
        "start_time",
        "venue",
        "city",
        "team1_id",
        "team2_id",
        "team1_name",
        "team2_name",
        "toss_winner_id",
        "toss_decision",
        "winner_id",
        "result_type",
        "result_margin",
        "player_of_match_id",
        "scorecard_url",
        "commentary_url",
        "bundle_ball_by_ball_status",
        "bundle_ball_by_ball_source",
        "bundle_scorecard_status",
        "source_url",
    ]
    m = m[keep].rename(
        columns={
            "bundle_ball_by_ball_status": "ball_by_ball_status",
            "bundle_ball_by_ball_source": "ball_by_ball_source",
            "bundle_scorecard_status": "scorecard_status",
        }
    )
    m["match_date"] = pd.to_datetime(m["match_date"]).dt.date
    m["start_time"] = pd.to_datetime(m["start_time"], utc=True, errors="coerce")
    m["match_number"] = _int(m["match_number"])

    # alias team ids -> real team ids
    amap = dict(zip(aliases["alias_id"], aliases["mapped_team_id"], strict=False))
    for col in ("winner_id", "toss_winner_id"):
        m[f"{col}_source"] = m[col]
        m[col] = m[col].map(lambda v: amap.get(v, v) if pd.notna(v) else v)
        m[f"{col}_corrected"] = m[f"{col}_source"].notna() & (m[f"{col}_source"] != m[col])

    # result text -> columns, tie-break winners
    parsed = pd.DataFrame(
        [parse_result(t, rt) for t, rt in zip(m["result_margin"], m["result_type"], strict=False)]
    )
    m = pd.concat([m.reset_index(drop=True), parsed], axis=1)
    name_to_id = {}
    for r in m.itertuples():
        name_to_id[(r.match_id, team_key(r.team1_name))] = r.team1_id
        name_to_id[(r.match_id, team_key(r.team2_name))] = r.team2_id
    m["winner_source"] = np.where(m["winner_id"].notna(), "result", None)
    tb = m["winner_id"].isna() & m["tie_break_winner_name"].notna()
    m.loc[tb, "winner_id"] = [
        name_to_id.get((r.match_id, team_key(r.tie_break_winner_name))) for r in m[tb].itertuples()
    ]
    m.loc[tb & m["winner_id"].notna(), "winner_source"] = "tie_break_text"
    # explicit, evidenced overrides (config/result_overrides.csv), e.g. a bowl-out the result text does not name
    ov_path = (root or Path(".")) / "config" / "result_overrides.csv"
    if ov_path.exists():
        for r in pd.read_csv(ov_path, dtype=str).itertuples():
            hit = m["match_id"] == r.match_id
            if not hit.any():
                raise ValueError(f"result override for unknown match {r.match_id}")
            row = m[hit].iloc[0]
            ids = {team_key(row.team1_name): row.team1_id, team_key(row.team2_name): row.team2_id}
            if team_key(r.winner_team_name) not in ids:
                raise ValueError(
                    f"override winner {r.winner_team_name} is not a participant of {r.match_id}"
                )
            m.loc[hit, "winner_id"] = ids[team_key(r.winner_team_name)]
            m.loc[hit, "winner_source"] = "manual_override"
            m.loc[hit, "tie_break_method"] = r.tie_break_method
    m["has_winner"] = m["winner_id"].notna()

    # stage taxonomy
    sched = bronze["match_schedule"][["match_id", "match_type", "source_title"]].drop_duplicates(
        "match_id"
    )
    m = m.merge(sched, on="match_id", how="left")
    title = m["source_title"].fillna("").str.lower()
    stage = m["match_stage"].copy()
    stage = stage.mask(title.str.contains("quarter"), "Quarterfinal")
    stage = stage.mask(stage.eq("Other") & title.str.contains("super"), "Super Six")
    gm = _group_clusters(bronze["standings"], m)
    lab = gm.drop_duplicates("match_id").set_index("match_id")
    in_round = ~stage.isin(KNOCKOUT) & m["match_id"].isin(lab.index)
    m["group_name"] = m["match_id"].map(lab["group_name"]) if len(lab) else None
    stage = stage.mask(in_round, m["match_id"].map(lab["round_label"]) if len(lab) else stage)
    m["group_name"] = m["group_name"].where(m["group_name"].notna(), _infer_groups(m, stage, bronze))
    m["match_stage_source"] = m["match_stage"]
    m["stage"] = stage
    m["is_knockout"] = m["stage"].isin(KNOCKOUT)

    m["venue_clean"] = (
        m["venue"].fillna("").str.replace(r"\s+", " ", regex=True).str.strip().replace("", None)
    )
    va_path = (root or Path(".")) / "config" / "venue_aliases.csv"
    vmap = (
        dict(pd.read_csv(va_path, dtype=str)[["alias_name", "canonical_name"]].values)
        if va_path.exists()
        else {}
    )
    m["venue_name_canonical"] = m["venue_clean"].map(
        lambda v: vmap.get(v, v) if isinstance(v, str) else None
    )
    m["venue_key"] = m["venue_name_canonical"].map(
        lambda v: norm(v) if isinstance(v, str) else None
    )
    return (
        m.drop(columns=["match_stage"])
        .sort_values(["tournament_id", "match_date", "match_id"])
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- deliveries / innings
def build_deliveries(
    bronze: dict[str, pd.DataFrame], idmap: pd.DataFrame, innings: pd.DataFrame
) -> pd.DataFrame:
    d = bronze["deliveries"].copy()
    d["innings_number"] = _int(d["innings_number"])
    lookup = idmap[["match_id", "source_name", "resolved_player_id", "source_id"]].copy()
    lookup["canonical"] = lookup["resolved_player_id"].fillna(lookup["source_id"])
    for col in NAME_COLUMNS:
        d[f"{col[:-3]}_name"] = d[col]
        merged = d[["match_id", col]].merge(
            lookup, left_on=["match_id", col], right_on=["match_id", "source_name"], how="left"
        )
        d[col] = merged["canonical"].to_numpy()
    for col in (
        "is_wide",
        "is_no_ball",
        "is_bye",
        "is_leg_bye",
        "is_penalty",
        "is_wicket",
        "is_legal_delivery",
    ):
        d[col] = _bool(d[col])
    for col in (
        "over_number",
        "ball_number",
        "delivery_sequence",
        "legal_ball_number",
        "batter_runs",
        "extra_runs",
        "total_runs",
    ):
        d[col] = _int(d[col])
    d = d.rename(columns={"is_legal_delivery": "is_not_wide"})
    # Cricsheet lists "retired hurt" as a wicket event, but the batter is not out: it is not a
    # team wicket and credits no bowler. The dismissal_type is kept for reference.
    d.loc[d["dismissal_type"].isin(NOT_A_DISMISSAL), "is_wicket"] = False
    d["is_legal_ball"] = ~(d["is_wide"].fillna(False) | d["is_no_ball"].fillna(False))
    d = d.sort_values(["match_id", "innings_number", "delivery_sequence"]).reset_index(drop=True)
    d["legal_delivery_number"] = (
        d.groupby(["match_id", "innings_number"])["is_legal_ball"].cumsum().astype("Int64")
    )
    teams = innings[["match_id", "innings_number", "batting_team_id", "bowling_team_id"]]
    d = d.merge(teams, on=["match_id", "innings_number"], how="left")
    cols = [
        "delivery_id",
        "match_id",
        "innings_id",
        "innings_number",
        "over_number",
        "ball_number",
        "delivery_sequence",
        "legal_delivery_number",
        "legal_ball_number",
        "batting_team_id",
        "bowling_team_id",
        "batter_id",
        "non_striker_id",
        "bowler_id",
        "batter_runs",
        "extra_runs",
        "total_runs",
        "extras_type",
        "is_wide",
        "is_no_ball",
        "is_bye",
        "is_leg_bye",
        "is_penalty",
        "is_legal_ball",
        "is_wicket",
        "dismissal_type",
        "dismissed_player_id",
        "fielder_id",
        "batter_name",
        "non_striker_name",
        "bowler_name",
        "dismissed_player_name",
        "fielder_name",
        "delivery_source",
        "source_url",
        "_source_file",
    ]
    return d[[c for c in cols if c in d.columns]]


def _balls_from_overs(overs: pd.Series) -> pd.Series:
    o = pd.to_numeric(overs, errors="coerce")
    whole = np.floor(o)
    return (whole * 6 + np.round((o - whole) * 10)).astype("Int64")


def build_innings(
    bronze: dict[str, pd.DataFrame],
    deliveries_raw: pd.DataFrame,
    idmap: pd.DataFrame,
    batting: pd.DataFrame,
    matches: pd.DataFrame,
) -> pd.DataFrame:
    inn = bronze["innings"].copy()
    inn["innings_number"] = _int(inn["innings_number"])
    for col in (
        "total_runs",
        "wickets",
        "extras",
        "byes",
        "legbyes",
        "wides",
        "noballs",
        "penalties",
        "target",
    ):
        inn[col] = _int(inn[col])
    inn["is_super_over"] = _bool(inn["is_super_over"]).fillna(False)
    inn["declared"] = _bool(inn["declared"])
    inn["legal_balls"] = _balls_from_overs(inn["overs"])
    inn["derived_from_deliveries"] = False
    inn["overs_source"] = inn["overs"]

    # Super Over (and any other) innings present in deliveries but missing from the scorecard innings.
    d = deliveries_raw
    have = set(zip(inn["match_id"], inn["innings_number"].astype(int), strict=False))
    agg = (
        d.groupby(["match_id", "innings_number"])
        .agg(
            total_runs=("total_runs", "sum"),
            wickets=("is_wicket", lambda s: int(s.fillna(False).sum())),
            legal_balls=("is_legal_ball", lambda s: int(s.sum())),
            batter=("batter_id", "first"),
            bowler=("bowler_id", "first"),
        )
        .reset_index()
    )
    team_of = batting.drop_duplicates(["match_id", "player_id"]).set_index(
        ["match_id", "player_id"]
    )["team_id"]
    new = []
    for r in agg.itertuples():
        if (r.match_id, int(r.innings_number)) in have:
            continue
        bat_team = team_of.get((r.match_id, r.batter))
        bowl_team = team_of.get((r.match_id, r.bowler))
        new.append(
            {
                "innings_id": f"{r.match_id}_{int(r.innings_number)}",
                "match_id": r.match_id,
                "innings_number": int(r.innings_number),
                "innings_type": "super_over",
                "batting_team_id": bat_team,
                "bowling_team_id": bowl_team,
                "total_runs": int(r.total_runs),
                "wickets": r.wickets,
                "overs": r.legal_balls // 6 + (r.legal_balls % 6) / 10,
                "legal_balls": r.legal_balls,
                "is_super_over": True,
                "derived_from_deliveries": True,
                "source_url": None,
            }
        )
    if new:
        inn = pd.concat([inn, pd.DataFrame(new)], ignore_index=True)
    inn["innings_number"] = _int(inn["innings_number"])
    inn["overs"] = pd.to_numeric(inn["overs"], errors="coerce")

    # overs missing for a normal innings that has deliveries: derive from legal balls
    leg = (
        d.groupby(["match_id", "innings_number"])["is_legal_ball"]
        .sum()
        .rename("legal_from_deliveries")
        .reset_index()
    )
    inn = inn.merge(leg, on=["match_id", "innings_number"], how="left")
    miss = inn["legal_balls"].isna() & inn["legal_from_deliveries"].notna()
    inn.loc[miss, "legal_balls"] = inn.loc[miss, "legal_from_deliveries"].astype("Int64")
    inn.loc[miss, "overs"] = inn.loc[miss, "legal_balls"].map(lambda b: b // 6 + (b % 6) / 10)
    inn["legal_balls"] = _int(inn["legal_balls"])
    inn = inn.drop(columns=["legal_from_deliveries"])
    return inn.sort_values(["match_id", "innings_number"]).reset_index(drop=True)


# --------------------------------------------------------------------------- scorecards
NOT_A_DISMISSAL = {"not out", "retired hurt", "absent hurt", "absent", "did not bat"}


def build_batting(bronze: dict[str, pd.DataFrame]) -> pd.DataFrame:
    b = bronze["scorecards/batting"].copy()
    for col in ("innings_number", "batting_position", "runs", "balls_faced", "fours", "sixes"):
        b[col] = _int(b[col])
    b["strike_rate"] = pd.to_numeric(b["strike_rate"], errors="coerce")
    for col in ("dismissal", "dismissal_type", "dismissed_by", "fielder"):
        b[col] = b[col].map(lambda v: v.strip() if isinstance(v, str) else v).replace("", None)
    b["did_bat"] = b["runs"].notna()
    kind = b["dismissal_type"].fillna("").str.strip().str.lower()
    b["is_out"] = b["did_bat"] & ~kind.isin(NOT_A_DISMISSAL) & kind.ne("")
    b["batting_scorecard_id"] = (
        b["match_id"] + "_" + b["innings_number"].astype(str) + "_" + b["player_id"]
    ).astype(str)
    cols = [
        "batting_scorecard_id",
        "match_id",
        "innings_id",
        "innings_number",
        "player_id",
        "player_name",
        "team_id",
        "batting_position",
        "did_bat",
        "runs",
        "balls_faced",
        "fours",
        "sixes",
        "strike_rate",
        "is_out",
        "dismissal_type",
        "dismissal",
        "dismissed_by",
        "fielder",
        "source_url",
    ]
    return b[[c for c in cols if c in b.columns]]


def build_bowling(bronze: dict[str, pd.DataFrame]) -> pd.DataFrame:
    w = bronze["scorecards/bowling"].copy()
    for col in (
        "innings_number",
        "maidens",
        "runs_conceded",
        "wickets",
        "dots",
        "wides",
        "no_balls",
    ):
        w[col] = _int(w[col])
    w["overs"] = pd.to_numeric(w["overs"], errors="coerce")
    w["balls_bowled"] = _balls_from_overs(w["overs"])
    w["economy"] = pd.to_numeric(w["economy"], errors="coerce")
    w["bowling_scorecard_id"] = (
        w["match_id"] + "_" + w["innings_number"].astype(str) + "_" + w["player_id"]
    ).astype(str)
    cols = [
        "bowling_scorecard_id",
        "match_id",
        "innings_id",
        "innings_number",
        "player_id",
        "player_name",
        "team_id",
        "overs",
        "balls_bowled",
        "maidens",
        "runs_conceded",
        "wickets",
        "economy",
        "dots",
        "wides",
        "no_balls",
        "source_url",
    ]
    return w[[c for c in cols if c in w.columns]]


def build_fielding(bronze: dict[str, pd.DataFrame]) -> pd.DataFrame:
    f = bronze["scorecards/fielding"].copy()
    for col in ("catches", "run_outs", "stumpings"):
        f[col] = _int(f[col]).fillna(0)
    return f[
        [
            "match_id",
            "player_id",
            "player_name",
            "team_id",
            "catches",
            "run_outs",
            "stumpings",
            "source_url",
        ]
    ]


# --------------------------------------------------------------------------- players / reference
def build_players(bronze: dict[str, pd.DataFrame], idmap: pd.DataFrame) -> pd.DataFrame:
    base = bronze["players"].copy()
    squads = bronze["squads"].copy()
    attrs = [
        "full_name",
        "batting_name",
        "source_player_id",
        "batting_style",
        "bowling_style",
        "date_of_birth",
    ]
    allp = pd.concat(
        [base[["player_id", *attrs]], squads[["player_id", *attrs]]], ignore_index=True
    )
    espn = allp.groupby("player_id", as_index=False)[attrs].first()  # first non-null per column
    espn["identity_source"] = "espn"

    resolved = idmap[idmap["resolved_player_id"].notna()]
    alias = resolved.groupby("resolved_player_id").agg(
        cricsheet_names=("source_name", lambda s: sorted(set(s))),
        cricsheet_ids=("source_id", lambda s: sorted(set(s))),
    )
    espn = espn.merge(alias, left_on="player_id", right_index=True, how="left")
    espn["cricsheet_names"] = espn["cricsheet_names"].map(
        lambda v: json.dumps(v) if isinstance(v, list) else None
    )
    espn["cricsheet_ids"] = espn["cricsheet_ids"].map(
        lambda v: json.dumps(v) if isinstance(v, list) else None
    )

    orphans = idmap[idmap["resolved_player_id"].isna()].drop_duplicates("source_id")
    extra = pd.DataFrame(
        {
            "player_id": orphans["source_id"],
            "full_name": orphans["source_name"],
            "batting_name": orphans["source_name"],
            "source_player_id": None,
            "batting_style": None,
            "bowling_style": None,
            "date_of_birth": None,
            "identity_source": "cricsheet_only",
            "cricsheet_names": orphans["source_name"].map(lambda v: json.dumps([v])),
            "cricsheet_ids": orphans["source_id"].map(lambda v: json.dumps([v])),
        }
    )
    extra = extra[~extra["player_id"].isin(espn["player_id"])]
    out = pd.concat([espn, extra], ignore_index=True)
    out["date_of_birth"] = pd.to_datetime(out["date_of_birth"], errors="coerce").dt.date
    return out.sort_values("player_id").reset_index(drop=True)


def build_squads(bronze: dict[str, pd.DataFrame]) -> pd.DataFrame:
    s = bronze["squads"].copy()
    s["source"] = "espncricinfo"
    man = bronze.get("manual_squads")
    if man is not None and len(man):
        teams = bronze["teams_registry"].set_index("team_name")["team_id"]
        pid = man["player_id"].where(man["player_id"].fillna("") != "")
        # manual rows rely on exact ESPN names; resolve here from bronze players
        names = bronze["players"].drop_duplicates("player_id")
        names = names[names["player_id"].str.startswith("espn_")].set_index("full_name")[
            "player_id"
        ]
        names = names[~names.index.duplicated(keep=False)]
        man = man.assign(
            team_id=man["team_name"].map(teams),
            player_id=pid.fillna(man["player_name"].map(names)),
            is_captain=_bool(man["is_captain"]),
            is_wicketkeeper=_bool(man["is_wicketkeeper"]),
            playing_roles=man["playing_role"],
            is_withdrawn=False,
            source="manual (user-supplied)",
        )
        s = pd.concat(
            [
                s,
                man[
                    [
                        "tournament_id",
                        "team_id",
                        "team_name",
                        "player_id",
                        "role_code",
                        "is_captain",
                        "is_wicketkeeper",
                        "playing_roles",
                        "is_withdrawn",
                        "source",
                        "note",
                    ]
                ],
            ],
            ignore_index=True,
        )
    for col in ("is_captain", "is_wicketkeeper", "is_withdrawn"):
        s[col] = _bool(s[col]).fillna(False)
    return s.drop_duplicates(["tournament_id", "team_id", "player_id"], keep="last").reset_index(
        drop=True
    )


def build_standings(
    bronze: dict[str, pd.DataFrame], matches: pd.DataFrame, teams: pd.DataFrame
) -> pd.DataFrame:
    st = bronze["standings"].copy()
    for col in ("position", "matches_played", "wins", "losses", "ties", "no_results"):
        st[col] = _int(st[col])
    for col in ("points", "net_run_rate"):
        st[col] = pd.to_numeric(st[col], errors="coerce")
    st["qualified"] = _bool(st["qualified"])
    return st.drop(columns=[c for c in ("group_match_ids",) if c in st.columns])


def build_awards(bronze: dict[str, pd.DataFrame]) -> pd.DataFrame:
    pom = bronze["awards"][["match_id", "award_type", "player_id"]].copy()
    pom = pom.merge(bronze["matches"][["match_id", "tournament_id"]], on="match_id")
    pom["award_scope"] = "match"
    teams = bronze["teams_registry"].set_index("team_name")["team_id"]
    names = bronze["players"].drop_duplicates("player_id")
    names = names[names["player_id"].str.startswith("espn_")].set_index("full_name")["player_id"]
    names = names[~names.index.duplicated(keep=False)]
    ta = bronze["tournament_awards"].copy()
    ta["player_id"] = ta["player_name"].map(names)
    ta["team_id"] = ta["team_name"].map(teams)
    ta["award_type"] = ta["award_type"].str.upper()
    ta["award_scope"] = "tournament"
    ta["match_id"] = None
    return pd.concat(
        [
            pom,
            ta[["tournament_id", "award_scope", "award_type", "player_id", "team_id", "match_id"]],
        ],
        ignore_index=True,
    )


# --------------------------------------------------------------------------- orchestration
def build_silver(root: Path) -> dict[str, Any]:
    names = [
        "matches",
        "innings",
        "players",
        "scorecards/batting",
        "scorecards/bowling",
        "scorecards/fielding",
        "deliveries",
        "teams",
        "teams_registry",
        "standings",
        "squads",
        "tournaments",
        "match_schedule",
        "awards",
        "tournament_awards",
        "manual_squads",
    ]
    bronze = {n: read_bronze(root, n) for n in names}
    report: dict[str, Any] = {}

    aliases = resolve_team_aliases(bronze["matches"])
    teams = build_teams(bronze, aliases)
    matches = build_matches(bronze, aliases, teams, root)

    raw_inn = bronze["innings"].copy()
    raw_inn["innings_number"] = _int(raw_inn["innings_number"])
    idmap, summary = build_identity_map(
        bronze["deliveries"],
        bronze["players"],
        bronze["scorecards/batting"],
        bronze["scorecards/bowling"],
        bronze["scorecards/fielding"],
        raw_inn.assign(innings_number=raw_inn["innings_number"].astype(int)),
    )
    report["identity"] = summary
    report["team_aliases"] = aliases.to_dict("records")

    batting = build_batting(bronze)
    bowling = build_bowling(bronze)
    fielding = build_fielding(bronze)
    deliveries0 = build_deliveries(
        bronze, idmap, raw_inn.assign(innings_number=raw_inn["innings_number"].astype(int))
    )
    innings = build_innings(bronze, deliveries0, idmap, batting, matches)
    deliveries = build_deliveries(
        bronze, idmap, innings.assign(innings_number=innings["innings_number"].astype(int))
    )
    players = build_players(bronze, idmap)

    tournaments = bronze["tournaments"].drop(columns=["_source_file"], errors="ignore").copy()
    tournaments["start_date"] = pd.to_datetime(tournaments["start_date"]).dt.date
    tournaments["end_date"] = pd.to_datetime(tournaments["end_date"]).dt.date
    tournaments["year"] = _int(tournaments["year"])
    tournaments["number_of_teams"] = _int(tournaments["number_of_teams"])
    tournaments["number_of_matches"] = (
        tournaments["tournament_id"].map(matches.groupby("tournament_id").size()).astype("Int64")
    )

    for entity, df in (
        ("tournaments", tournaments),
        ("teams", teams),
        ("matches", matches),
        ("innings", innings),
        ("deliveries", deliveries),
        ("players", players),
        ("batting", batting),
        ("bowling", bowling),
        ("fielding", fielding),
        ("squads", build_squads(bronze)),
        ("standings", build_standings(bronze, matches, teams)),
        ("awards", build_awards(bronze)),
        ("player_identity_map", idmap),
        ("team_aliases", aliases),
    ):
        report[entity] = _write(root, entity, df)
    return report
