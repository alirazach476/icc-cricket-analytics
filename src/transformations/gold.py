"""Gold layer: analytical dimensions, facts and marts built from silver (Stage 4).

Business-friendly names and consistent metric definitions. Every metric is computed here once so the
dashboard, SQL and models share it:

* batting average = runs / (innings batted - not outs); strike rate = runs / balls faced x 100
* bowling average = runs conceded / wickets; economy = runs conceded / overs; overs from legal balls
* phases (1-based over numbers): T20 powerplay 1-6, middle 7-15, death 16-20;
  ODI powerplay 1-10, middle 11-40, death 41-50 (a modern simplification, applied to all editions)
* dot ball = a legal ball with no runs off it; boundary = four or six hit off the bat
* ball-by-ball metrics are null where ball-by-ball data does not exist (never zero-filled)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.transformations.silver import read_silver

# last over of powerplay, last over of middle. Tests have no powerplays: overs 1-15 = new ball, 16-80 = middle,
# 81+ = old ball / second new ball (stored under the same three labels).
PHASES = {"T20": (6, 15), "ODI": (10, 40), "Test": (15, 80)}
STAGE_ORDER = [
    "Group Stage",
    "First Round",
    "Super Six",
    "Super Eight",
    "Super Ten",
    "Super 12",
    "Quarterfinal",
    "Semifinal",
    "Final",
]


def _write(root: Path, name: str, df: pd.DataFrame) -> dict[str, Any]:
    out = root / "data" / "gold" / name
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "part-0.parquet.tmp"
    df.to_parquet(tmp, index=False)
    tmp.replace(out / "part-0.parquet")
    return {"table": name, "rows": int(len(df)), "columns": int(len(df.columns))}


def read_gold(root: Path, name: str) -> pd.DataFrame:
    return pd.read_parquet(root / "data" / "gold" / name / "part-0.parquet")


def _div(a, b, nd=2):
    return (a / b.where(b > 0)).round(nd)


# --------------------------------------------------------------------------- dimensions
def dim_tournaments(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    t = S["tournaments"].copy()
    teams = S["teams"].set_index("team_name")["team_id"]
    t["winner_team_id"] = t["winner"].map(teams)
    t["runner_up_team_id"] = t["runner_up"].map(teams)
    pott = S["awards"].query(
        "award_scope == 'tournament' and award_type == 'PLAYER_OF_THE_TOURNAMENT'"
    )
    t["player_of_tournament_id"] = t["tournament_id"].map(
        pott.set_index("tournament_id")["player_id"]
    )
    return t.drop(columns=["collection_status", "completion_status"], errors="ignore")


def dim_teams(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return S["teams"][["team_id", "team_name", "short_name", "team_key", "source_team_id"]].copy()


def dim_players(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    p = S["players"].copy()
    p["has_ball_by_ball_alias"] = p["cricsheet_ids"].notna()
    return p


def dim_venues(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    m = S["matches"][
        [
            "match_id",
            "tournament_id",
            "match_date",
            "venue_clean",
            "venue_name_canonical",
            "venue_key",
            "city",
        ]
    ].dropna(subset=["venue_key"])
    g = (
        m.groupby("venue_key")
        .agg(
            venue_name=("venue_name_canonical", lambda s: s.mode().iat[0]),
            name_variants=("venue_clean", lambda s: " | ".join(sorted(set(s)))),
            city=("city", lambda s: s.mode().iat[0] if s.notna().any() else None),
            matches=("match_id", "nunique"),
            first_year=("match_date", lambda s: min(s).year),
            last_year=("match_date", lambda s: max(s).year),
        )
        .reset_index()
    )
    g["venue_id"] = "ven_" + g["venue_key"].str.replace(" ", "_")
    # Candidate duplicates (same city, similar ground name) are flagged for review, never merged.
    from difflib import SequenceMatcher

    flag = {}
    for _city, sub in g.groupby("city"):
        rows = list(sub.itertuples())
        for a in range(len(rows)):
            for b in range(a + 1, len(rows)):
                if SequenceMatcher(None, rows[a].venue_key, rows[b].venue_key).ratio() >= 0.8:
                    flag[rows[b].venue_id] = rows[a].venue_id
    g["possible_duplicate_of"] = g["venue_id"].map(flag)
    return (
        g[
            [
                "venue_id",
                "venue_name",
                "city",
                "matches",
                "first_year",
                "last_year",
                "name_variants",
                "possible_duplicate_of",
                "venue_key",
            ]
        ]
        .sort_values("venue_id")
        .reset_index(drop=True)
    )


def dim_dates(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d = pd.to_datetime(S["matches"]["match_date"])
    days = pd.date_range(d.min(), d.max(), freq="D")
    return pd.DataFrame(
        {
            "date_key": days.strftime("%Y%m%d").astype(int),
            "date": days.date,
            "year": days.year,
            "month": days.month,
            "month_name": days.strftime("%B"),
            "day": days.day,
            "weekday": days.strftime("%A"),
            "is_weekend": days.dayofweek >= 5,
        }
    )


# --------------------------------------------------------------------------- facts
def _phase(over: pd.Series, fmt: pd.Series) -> pd.Series:
    pp = fmt.map(lambda f: PHASES[f][0])
    mid = fmt.map(lambda f: PHASES[f][1])
    return pd.Series(
        np.where(over <= pp, "powerplay", np.where(over <= mid, "middle", "death")),
        index=over.index,
    )


def fact_deliveries(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d = S["deliveries"].copy()
    m = S["matches"][["match_id", "tournament_id", "stage", "match_date"]].merge(
        S["tournaments"][["tournament_id", "format", "year"]], on="tournament_id"
    )
    d = d.merge(m, on="match_id", how="left")
    super_over = S["innings"].set_index("innings_id")["is_super_over"]
    d["is_super_over"] = d["innings_id"].map(super_over).fillna(False).astype(bool)
    over = d["over_number"].astype(float)
    d["phase"] = np.where(d["is_super_over"], "super_over", _phase(over, d["format"]))
    legal = d["is_legal_ball"].astype(bool)
    d["is_dot_ball"] = legal & (d["total_runs"] == 0)
    d["is_four"] = (
        d["batter_runs"].eq(4) & ~d["is_bye"].fillna(False) & ~d["is_leg_bye"].fillna(False)
    )
    d["is_six"] = d["batter_runs"].eq(6)
    d["is_boundary"] = d["is_four"] | d["is_six"]
    d = d.sort_values(["match_id", "innings_number", "delivery_sequence"])
    key = [d["match_id"], d["innings_number"]]
    d["cumulative_runs"] = d.groupby(key)["total_runs"].cumsum().astype("Int64")
    d["cumulative_wickets"] = (
        d.groupby(key)["is_wicket"]
        .transform(lambda s: s.fillna(False).astype(int).cumsum())
        .astype("Int64")
    )
    d["balls_bowled_in_innings"] = d["legal_delivery_number"]
    cols = [
        "delivery_id",
        "match_id",
        "tournament_id",
        "format",
        "year",
        "stage",
        "match_date",
        "innings_id",
        "innings_number",
        "is_super_over",
        "over_number",
        "ball_number",
        "delivery_sequence",
        "legal_delivery_number",
        "phase",
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
        "is_dot_ball",
        "is_four",
        "is_six",
        "is_boundary",
        "is_wicket",
        "dismissal_type",
        "dismissed_player_id",
        "fielder_id",
        "cumulative_runs",
        "cumulative_wickets",
    ]
    return d[cols].reset_index(drop=True)


def fact_innings(S: dict[str, pd.DataFrame], fd: pd.DataFrame) -> pd.DataFrame:
    inn = S["innings"].copy()
    names = S["teams"].set_index("team_id")["team_name"]
    m = S["matches"][["match_id", "tournament_id", "stage", "match_date", "winner_id"]].merge(
        S["tournaments"][["tournament_id", "format", "year"]], on="tournament_id"
    )
    inn = inn.merge(m, on="match_id", how="left")
    inn["batting_team"] = inn["batting_team_id"].map(names)
    inn["bowling_team"] = inn["bowling_team_id"].map(names)
    chase_innings = np.where(
        inn["format"].eq("Test"), 4, 2
    )  # the last innings of a Test is the chase
    inn["is_chase"] = inn["innings_number"].eq(chase_innings) & ~inn["is_super_over"]
    inn["is_winner_batting"] = np.where(
        inn["winner_id"].notna(), inn["batting_team_id"] == inn["winner_id"], None
    )
    inn["run_rate"] = _div(
        inn["total_runs"].astype(float), (inn["legal_balls"] / 6).astype(float), 3
    )
    inn["runs_per_wicket"] = _div(inn["total_runs"].astype(float), inn["wickets"].astype(float), 2)

    bat = (
        S["batting"]
        .groupby(["match_id", "innings_number"])
        .agg(fours=("fours", "sum"), sixes=("sixes", "sum"))
        .reset_index()
    )
    bat["innings_number"] = bat["innings_number"].astype(int)
    inn["innings_number"] = inn["innings_number"].astype(int)
    inn = inn.merge(bat, on=["match_id", "innings_number"], how="left")
    inn["boundary_runs"] = (4 * inn["fours"] + 6 * inn["sixes"]).astype("Int64")
    inn["boundary_run_pct"] = (
        _div(inn["boundary_runs"].astype(float), inn["total_runs"].astype(float), 1) * 100 / 1
    )

    f = fd[~fd["is_super_over"]].copy()
    f["innings_number"] = f["innings_number"].astype(int)
    ph = (
        f.groupby(["match_id", "innings_number", "phase"])
        .agg(runs=("total_runs", "sum"), wkts=("is_wicket", lambda s: int(s.fillna(False).sum())))
        .reset_index()
    )
    wide = ph.pivot(index=["match_id", "innings_number"], columns="phase", values=["runs", "wkts"])
    wide.columns = [f"{'wickets' if a == 'wkts' else 'runs'}_{b}" for a, b in wide.columns]
    wide = wide.reset_index().rename(
        columns={
            c: c.replace("powerplay", "powerplay")
            .replace("middle", "middle_overs")
            .replace("death", "death_overs")
            for c in wide.columns
        }
    )
    tot = (
        f.groupby(["match_id", "innings_number"])
        .agg(
            dot_balls=("is_dot_ball", "sum"),
            legal_from_bbb=("is_legal_ball", "sum"),
            bbb_boundaries=("is_boundary", "sum"),
        )
        .reset_index()
    )
    inn = inn.merge(wide, on=["match_id", "innings_number"], how="left").merge(
        tot, on=["match_id", "innings_number"], how="left"
    )
    inn["dot_ball_pct"] = (
        _div(inn["dot_balls"].astype(float), inn["legal_from_bbb"].astype(float), 4) * 100
    )
    inn["has_ball_by_ball"] = inn["legal_from_bbb"].notna()
    keep = [
        "innings_id",
        "match_id",
        "tournament_id",
        "format",
        "year",
        "stage",
        "match_date",
        "innings_number",
        "is_super_over",
        "is_chase",
        "batting_team_id",
        "batting_team",
        "bowling_team_id",
        "bowling_team",
        "total_runs",
        "wickets",
        "overs",
        "legal_balls",
        "run_rate",
        "runs_per_wicket",
        "extras",
        "wides",
        "noballs",
        "byes",
        "legbyes",
        "penalties",
        "target",
        "fours",
        "sixes",
        "boundary_runs",
        "boundary_run_pct",
        "runs_powerplay",
        "runs_middle_overs",
        "runs_death_overs",
        "wickets_powerplay",
        "wickets_middle_overs",
        "wickets_death_overs",
        "dot_balls",
        "dot_ball_pct",
        "is_winner_batting",
        "derived_from_deliveries",
        "has_ball_by_ball",
    ]
    return inn[[c for c in keep if c in inn.columns]]


def fact_matches(
    S: dict[str, pd.DataFrame], fi: pd.DataFrame, venues: pd.DataFrame
) -> pd.DataFrame:
    m = S["matches"].copy()
    names = S["teams"].set_index("team_id")["team_name"]
    t = S["tournaments"][["tournament_id", "format", "year", "tournament_name"]]
    m = m.merge(t, on="tournament_id")
    vmap = venues.set_index("venue_key")["venue_id"]
    m["venue_id"] = m["venue_key"].map(vmap)
    m["date_key"] = pd.to_datetime(m["match_date"]).dt.strftime("%Y%m%d").astype(int)
    for col in ("team1", "team2", "winner", "toss_winner"):
        src = f"{col}_id"
        m[f"{col}_name"] = (
            m[src].map(names) if col != "team1" and col != "team2" else m[f"{col}_name"]
        )
    m["loser_id"] = np.where(
        m["has_winner"],
        np.where(m["winner_id"] == m["team1_id"], m["team2_id"], m["team1_id"]),
        None,
    )

    n = fi[~fi["is_super_over"]]
    first = n[n["innings_number"] == 1].set_index("match_id")
    second = n[n["innings_number"] == 2].set_index("match_id")
    m["batting_first_team_id"] = m["match_id"].map(first["batting_team_id"])
    m["batting_second_team_id"] = m["match_id"].map(second["batting_team_id"])
    for pre, df in (("first", first), ("second", second)):
        m[f"{pre}_innings_runs"] = m["match_id"].map(df["total_runs"])
        m[f"{pre}_innings_wickets"] = m["match_id"].map(df["wickets"])
        m[f"{pre}_innings_overs"] = m["match_id"].map(df["overs"])
    m["target"] = m["match_id"].map(second["target"])
    played = m["result_type"].eq("RESULT") & ~m["is_walkover"]
    m["won_by_batting_first"] = np.where(
        played & m["has_winner"], m["winner_id"] == m["batting_first_team_id"], None
    )
    m["won_by_chasing"] = np.where(
        played & m["has_winner"], m["winner_id"] == m["batting_second_team_id"], None
    )
    m["toss_winner_won_match"] = np.where(
        m["has_winner"] & m["toss_winner_id"].notna(), m["winner_id"] == m["toss_winner_id"], None
    )
    m["toss_winner_batted_first"] = np.where(
        m["toss_winner_id"].notna(), m["toss_winner_id"] == m["batting_first_team_id"], None
    )
    so = fi[fi["is_super_over"]].groupby("match_id").size()
    m["went_to_super_over"] = m["match_id"].map(so).fillna(0).gt(0) | m["tie_break_method"].eq(
        "super over"
    )
    tot = n.groupby("match_id").agg(
        match_runs=("total_runs", "sum"),
        match_wickets=("wickets", "sum"),
        match_fours=("fours", "sum"),
        match_sixes=("sixes", "sum"),
    )
    m = m.merge(tot, left_on="match_id", right_index=True, how="left")
    m["has_ball_by_ball"] = m["ball_by_ball_status"].eq("complete")
    m["ball_by_ball_gap_reason"] = np.select(
        [
            m["has_ball_by_ball"],
            m["is_walkover"],
            ~m["result_type"].eq("RESULT"),
        ],
        [None, "walkover_no_play", "no_result_or_abandoned"],
        # Verified: every one of Cricsheet's World Cup matches is already linked, so these are not in the bundle.
        default="not_in_cricsheet_world_cup_bundle",
    )
    m["ball_by_ball_gap_reason"] = m["ball_by_ball_gap_reason"].replace("None", None)
    m["is_completed"] = m["result_type"].eq("RESULT")
    keep = [
        "match_id",
        "tournament_id",
        "tournament_name",
        "format",
        "year",
        "match_date",
        "date_key",
        "stage",
        "is_knockout",
        "group_name",
        "match_number",
        "venue_id",
        "venue_clean",
        "city",
        "team1_id",
        "team1_name",
        "team2_id",
        "team2_name",
        "toss_winner_id",
        "toss_decision",
        "winner_id",
        "winner_name",
        "loser_id",
        "winner_source",
        "result_type",
        "result_margin",
        "margin_type",
        "margin_value",
        "balls_remaining",
        "is_completed",
        "is_tie",
        "tie_break_method",
        "is_dls",
        "is_walkover",
        "went_to_super_over",
        "batting_first_team_id",
        "batting_second_team_id",
        "first_innings_runs",
        "first_innings_wickets",
        "first_innings_overs",
        "second_innings_runs",
        "second_innings_wickets",
        "second_innings_overs",
        "target",
        "won_by_batting_first",
        "won_by_chasing",
        "toss_winner_won_match",
        "toss_winner_batted_first",
        "match_runs",
        "match_wickets",
        "match_fours",
        "match_sixes",
        "player_of_match_id",
        "has_ball_by_ball",
        "ball_by_ball_gap_reason",
        "winner_id_corrected",
        "toss_winner_id_corrected",
        "source_url",
    ]
    return (
        m[[c for c in keep if c in m.columns]]
        .sort_values(["tournament_id", "match_date", "match_id"])
        .reset_index(drop=True)
    )


def _in_keys(df: pd.DataFrame, keys: set[tuple[str, int]]) -> pd.Series:
    """Boolean row mask (safe for empty frames, unlike indexing with a list of bools)."""
    return pd.Series(
        [(m, n) in keys for m, n in zip(df["match_id"], df["innings_number"], strict=False)],
        index=df.index,
        dtype=bool,
    )


def _super_over_keys(S: dict[str, pd.DataFrame]) -> set[tuple[str, int]]:
    inn = S["innings"]
    so = inn[inn["is_super_over"].fillna(False).astype(bool)]
    return set(zip(so["match_id"], so["innings_number"].astype(int), strict=False))


def fact_super_over_performances(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Super Over batting and bowling, kept out of regular statistics (cricket records exclude them)."""
    keys = _super_over_keys(S)
    b = S["batting"].copy()
    b["innings_number"] = b["innings_number"].astype(int)
    bat = b[_in_keys(b, keys)]
    bat = bat[
        [
            "match_id",
            "innings_number",
            "player_id",
            "team_id",
            "runs",
            "balls_faced",
            "fours",
            "sixes",
            "is_out",
        ]
    ]
    w = S["bowling"].copy()
    w["innings_number"] = w["innings_number"].astype(int)
    bowl = w[_in_keys(w, keys)]
    bowl = bowl[
        [
            "match_id",
            "innings_number",
            "player_id",
            "team_id",
            "balls_bowled",
            "runs_conceded",
            "wickets",
        ]
    ]
    out = pd.concat([bat.assign(role="bat"), bowl.assign(role="bowl")], ignore_index=True)
    return out.sort_values(["match_id", "innings_number", "role", "player_id"]).reset_index(
        drop=True
    )


def fact_player_performances(S: dict[str, pd.DataFrame], fm: pd.DataFrame) -> pd.DataFrame:
    so_keys = _super_over_keys(S)
    b = S["batting"].copy()
    w = S["bowling"].copy()
    f = S["fielding"].copy()
    b["innings_number"] = b["innings_number"].astype(int)
    w["innings_number"] = w["innings_number"].astype(int)
    b = b[~_in_keys(b, so_keys)]
    w = w[~_in_keys(w, so_keys)]
    keys = ["match_id", "player_id"]
    bat = b[
        keys
        + [
            "team_id",
            "innings_number",
            "batting_position",
            "did_bat",
            "runs",
            "balls_faced",
            "fours",
            "sixes",
            "strike_rate",
            "is_out",
            "dismissal_type",
        ]
    ].rename(columns={"innings_number": "batting_innings"})
    bowl = w[
        keys
        + [
            "team_id",
            "balls_bowled",
            "overs",
            "maidens",
            "runs_conceded",
            "wickets",
            "economy",
            "dots",
            "wides",
            "no_balls",
        ]
    ]
    bowl = bowl.rename(columns={"team_id": "bowl_team_id"})
    # one batting row per player-match; bowlers may have more than one row only in unusual cases: aggregate
    bowl = bowl.groupby(keys + ["bowl_team_id"], as_index=False).agg(
        balls_bowled=("balls_bowled", "sum"),
        maidens=("maidens", "sum"),
        runs_conceded=("runs_conceded", "sum"),
        wickets=("wickets", "sum"),
        dots=("dots", "sum"),
        wides=("wides", "sum"),
        no_balls=("no_balls", "sum"),
    )
    fld = f[keys + ["team_id", "catches", "run_outs", "stumpings"]].rename(
        columns={"team_id": "field_team_id"}
    )
    p = bat.merge(bowl, on=keys, how="outer").merge(fld, on=keys, how="outer")
    p["team_id"] = p["team_id"].fillna(p["bowl_team_id"]).fillna(p["field_team_id"])
    p = p.drop(columns=["bowl_team_id", "field_team_id"])
    # Tests: a player can have two batting rows in one match (one per innings). Bowling and fielding are
    # match totals, so they are kept on the first row only (otherwise they would be counted twice).
    dup = p.duplicated(["match_id", "player_id"], keep="first")
    for c in (
        "balls_bowled",
        "maidens",
        "runs_conceded",
        "wickets",
        "dots",
        "wides",
        "no_balls",
        "catches",
        "run_outs",
        "stumpings",
    ):
        p.loc[dup, c] = pd.NA
    p["did_bat"] = p["did_bat"].fillna(False).astype(bool)
    p["did_bowl"] = p["balls_bowled"].notna()
    p["overs_bowled"] = (p["balls_bowled"] / 6).round(3)
    p["economy"] = _div(p["runs_conceded"].astype(float), p["overs_bowled"].astype(float), 2)
    for c in ("catches", "run_outs", "stumpings"):
        p[c] = p[c].fillna(0).astype("Int64")
    mm = fm[
        [
            "match_id",
            "tournament_id",
            "format",
            "year",
            "stage",
            "is_knockout",
            "match_date",
            "team1_id",
            "team2_id",
            "winner_id",
            "has_ball_by_ball",
            "player_of_match_id",
        ]
    ]
    p = p.merge(mm, on="match_id", how="left")
    p["opposition_team_id"] = np.where(p["team_id"] == p["team1_id"], p["team2_id"], p["team1_id"])
    p["team_won"] = np.where(p["winner_id"].notna(), p["team_id"] == p["winner_id"], None)
    p["is_player_of_match"] = p["player_id"] == p["player_of_match_id"]
    p = p.drop(columns=["team1_id", "team2_id", "winner_id", "player_of_match_id"])
    return p.sort_values(["tournament_id", "match_date", "match_id", "player_id"]).reset_index(
        drop=True
    )


def fact_tournament_standings(S: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # The canonical team name wins; the name as printed on the source page is dropped, which
    # also avoids a team_name_x/team_name_y clash in the merge.
    base = S["standings"].drop(columns=["team_name"], errors="ignore")
    st = base.merge(S["teams"][["team_id", "team_name"]], on="team_id", how="left")
    return st.drop(
        columns=[
            "runs_for",
            "runs_against",
            "source_name",
            "source_url",
            "collected_at",
            "_source_file",
        ],
        errors="ignore",
    )


# --------------------------------------------------------------------------- marts
def _bat_agg(g: pd.core.groupby.DataFrameGroupBy) -> pd.DataFrame:
    a = g.agg(
        matches=("match_id", "nunique"),
        innings=("did_bat", "sum"),
        not_outs=("not_out", "sum"),
        runs=("runs", "sum"),
        balls_faced=("balls_faced", "sum"),
        highest_score=("runs", "max"),
        fours=("fours", "sum"),
        sixes=("sixes", "sum"),
        fifties=("fifty", "sum"),
        hundreds=("hundred", "sum"),
        ducks=("duck", "sum"),
    ).reset_index()
    dismissals = a["innings"] - a["not_outs"]
    a["average"] = _div(a["runs"].astype(float), dismissals.astype(float), 2)
    a["strike_rate"] = (
        100 * _div(a["runs"].astype(float), a["balls_faced"].astype(float), 4)
    ).round(2)
    return a


def _bat_base(fp: pd.DataFrame) -> pd.DataFrame:
    b = fp[fp["did_bat"]].copy()
    b["not_out"] = ~b["is_out"].fillna(False)
    b["fifty"] = (b["runs"] >= 50) & (b["runs"] < 100)
    b["hundred"] = b["runs"] >= 100
    b["duck"] = (b["runs"] == 0) & b["is_out"].fillna(False)
    return b


def mart_batting(fp: pd.DataFrame, by_tournament: bool) -> pd.DataFrame:
    b = _bat_base(fp)
    keys = (
        ["player_id", "tournament_id", "format", "year"]
        if by_tournament
        else ["player_id", "format"]
    )
    out = _bat_agg(b.groupby(keys))
    if by_tournament:
        team = (
            b.groupby(["player_id", "tournament_id"])["team_id"]
            .agg(lambda s: s.mode().iat[0])
            .rename("team_id")
            .reset_index()
        )
        out = out.merge(team, on=["player_id", "tournament_id"])
    return out.sort_values("runs", ascending=False).reset_index(drop=True)


def mart_bowling(fp: pd.DataFrame, by_tournament: bool) -> pd.DataFrame:
    w = fp[fp["did_bowl"]].copy()
    w["four_wkts"] = w["wickets"] == 4
    w["five_wkts"] = w["wickets"] >= 5
    keys = (
        ["player_id", "tournament_id", "format", "year"]
        if by_tournament
        else ["player_id", "format"]
    )
    a = (
        w.groupby(keys)
        .agg(
            matches=("match_id", "nunique"),
            balls_bowled=("balls_bowled", "sum"),
            maidens=("maidens", "sum"),
            runs_conceded=("runs_conceded", "sum"),
            wickets=("wickets", "sum"),
            dots=("dots", "sum"),
            four_wicket_hauls=("four_wkts", "sum"),
            five_wicket_hauls=("five_wkts", "sum"),
        )
        .reset_index()
    )
    a["overs"] = (a["balls_bowled"] / 6).round(1)
    a["average"] = _div(a["runs_conceded"].astype(float), a["wickets"].astype(float), 2)
    a["economy"] = _div(a["runs_conceded"].astype(float), (a["balls_bowled"] / 6).astype(float), 2)
    a["strike_rate"] = _div(a["balls_bowled"].astype(float), a["wickets"].astype(float), 1)
    best = (
        w.sort_values(["wickets", "runs_conceded"], ascending=[False, True]).groupby(keys).head(1)
    )
    best["best_figures"] = (
        best["wickets"].astype(int).astype(str)
        + "/"
        + best["runs_conceded"].astype(int).astype(str)
    )
    a = a.merge(best[keys + ["best_figures"]], on=keys, how="left")
    if by_tournament:
        team = (
            w.groupby(["player_id", "tournament_id"])["team_id"]
            .agg(lambda s: s.mode().iat[0])
            .rename("team_id")
            .reset_index()
        )
        a = a.merge(team, on=["player_id", "tournament_id"])
    return a.sort_values("wickets", ascending=False).reset_index(drop=True)


def mart_team_performance(
    S: dict[str, pd.DataFrame], fm: pd.DataFrame, fi: pd.DataFrame
) -> pd.DataFrame:
    names = S["teams"].set_index("team_id")["team_name"]
    rows = []
    for side in ("team1_id", "team2_id"):
        x = fm[
            [
                "match_id",
                "tournament_id",
                "format",
                "year",
                "stage",
                "result_type",
                "is_tie",
                "winner_id",
                side,
            ]
        ].rename(columns={side: "team_id"})
        rows.append(x)
    t = pd.concat(rows)
    t["won"] = t["winner_id"] == t["team_id"]
    t["lost"] = t["winner_id"].notna() & (t["winner_id"] != t["team_id"])
    t["no_result"] = t["result_type"].isin(["NO RESULT", "ABANDONED"])
    t["tied_no_winner"] = t["is_tie"] & t["winner_id"].isna()
    g = (
        t.groupby(["team_id", "tournament_id", "format", "year"])
        .agg(
            matches=("match_id", "nunique"),
            wins=("won", "sum"),
            losses=("lost", "sum"),
            no_results=("no_result", "sum"),
            ties_no_winner=("tied_no_winner", "sum"),
        )
        .reset_index()
    )
    g["win_pct"] = _div(
        100 * g["wins"].astype(float), (g["matches"] - g["no_results"]).astype(float), 1
    )
    n = fi[~fi["is_super_over"]]
    bat = (
        n.groupby(["batting_team_id", "tournament_id"])
        .agg(
            avg_runs_scored=("total_runs", "mean"),
            highest_total=("total_runs", "max"),
            lowest_total=("total_runs", "min"),
            avg_run_rate=("run_rate", "mean"),
        )
        .reset_index()
        .rename(columns={"batting_team_id": "team_id"})
    )
    bowl = (
        n.groupby(["bowling_team_id", "tournament_id"])
        .agg(avg_runs_conceded=("total_runs", "mean"))
        .reset_index()
        .rename(columns={"bowling_team_id": "team_id"})
    )
    g = g.merge(bat, on=["team_id", "tournament_id"], how="left").merge(
        bowl, on=["team_id", "tournament_id"], how="left"
    )
    for c in ("avg_runs_scored", "avg_runs_conceded", "avg_run_rate"):
        g[c] = g[c].round(2)
    first = fm.assign(bf=fm["won_by_batting_first"], ch=fm["won_by_chasing"])
    wb = pd.concat(
        [
            first[["tournament_id", "batting_first_team_id", "bf"]]
            .rename(columns={"batting_first_team_id": "team_id", "bf": "w"})
            .assign(kind="wins_batting_first"),
            first[["tournament_id", "batting_second_team_id", "ch"]]
            .rename(columns={"batting_second_team_id": "team_id", "ch": "w"})
            .assign(kind="wins_chasing"),
        ]
    )
    wb = wb[wb["w"].notna()]
    wb["w"] = wb["w"].astype(bool)
    wbp = wb.pivot_table(
        index=["team_id", "tournament_id"], columns="kind", values="w", aggfunc="sum"
    ).reset_index()
    g = g.merge(wbp, on=["team_id", "tournament_id"], how="left")
    rank = {s: i for i, s in enumerate(STAGE_ORDER)}
    played = (
        t.assign(r=t["stage"].map(rank))
        .sort_values("r")
        .groupby(["team_id", "tournament_id"])
        .tail(1)
    )
    g = g.merge(
        played[["team_id", "tournament_id", "stage"]].rename(columns={"stage": "furthest_stage"}),
        on=["team_id", "tournament_id"],
        how="left",
    )
    champ = S["tournaments"].set_index("tournament_id")["winner"]
    g["team_name"] = g["team_id"].map(names)
    g["is_champion"] = g["team_name"] == g["tournament_id"].map(champ)
    return g.sort_values(["tournament_id", "wins"], ascending=[True, False]).reset_index(drop=True)


def mart_tournament_summary(
    S: dict[str, pd.DataFrame], fm: pd.DataFrame, fi: pd.DataFrame
) -> pd.DataFrame:
    n = fi[~fi["is_super_over"]]
    first = n[n["innings_number"] == 1].groupby("tournament_id")["total_runs"].mean().round(1)
    g = (
        fm.groupby(["tournament_id", "tournament_name", "format", "year"])
        .agg(
            matches=("match_id", "nunique"),
            completed=("is_completed", "sum"),
            total_runs=("match_runs", "sum"),
            total_wickets=("match_wickets", "sum"),
            fours=("match_fours", "sum"),
            sixes=("match_sixes", "sum"),
            ties=("is_tie", "sum"),
            dls_matches=("is_dls", "sum"),
            super_overs=("went_to_super_over", "sum"),
            matches_with_ball_by_ball=("has_ball_by_ball", "sum"),
            bat_first_wins=("won_by_batting_first", lambda s: int(s.dropna().astype(bool).sum())),
            chase_wins=("won_by_chasing", lambda s: int(s.dropna().astype(bool).sum())),
            toss_winner_won=("toss_winner_won_match", lambda s: int(s.dropna().astype(bool).sum())),
            toss_decided_matches=("toss_winner_won_match", lambda s: int(s.notna().sum())),
        )
        .reset_index()
    )
    g["avg_first_innings_score"] = g["tournament_id"].map(first)
    g["runs_per_match"] = _div(g["total_runs"].astype(float), g["completed"].astype(float), 1)
    g["bat_first_win_pct"] = _div(
        100 * g["bat_first_wins"].astype(float),
        (g["bat_first_wins"] + g["chase_wins"]).astype(float),
        1,
    )
    g["toss_winner_win_pct"] = _div(
        100 * g["toss_winner_won"].astype(float), g["toss_decided_matches"].astype(float), 1
    )
    g["ball_by_ball_coverage_pct"] = _div(
        100 * g["matches_with_ball_by_ball"].astype(float), g["matches"].astype(float), 1
    )
    dt = S["tournaments"][
        ["tournament_id", "winner", "runner_up", "host_country", "number_of_teams"]
    ]
    g = g.merge(dt, on="tournament_id")
    pott = S["awards"].query("award_scope == 'tournament'").set_index("tournament_id")["player_id"]
    pl = S["players"].set_index("player_id")["full_name"]
    g["player_of_tournament"] = g["tournament_id"].map(pott).map(pl)
    return (
        g.drop(columns=["toss_decided_matches"])
        .sort_values(["format", "year"])
        .reset_index(drop=True)
    )


def mart_data_coverage(S: dict[str, pd.DataFrame], fm: pd.DataFrame) -> pd.DataFrame:
    """What data exists per tournament, and why anything is missing (never claims full coverage)."""
    played = fm["is_completed"] & ~fm["is_walkover"]
    g = (
        fm.assign(played=played)
        .groupby(["tournament_id", "tournament_name", "format", "year"])
        .agg(
            matches=("match_id", "nunique"),
            played_matches=("played", "sum"),
            no_result_or_abandoned=("result_type", lambda s: int((s != "RESULT").sum())),
            walkovers=("is_walkover", "sum"),
            matches_with_ball_by_ball=("has_ball_by_ball", "sum"),
        )
        .reset_index()
    )
    bb_played = fm[played].groupby("tournament_id")["has_ball_by_ball"].sum()
    g["played_with_ball_by_ball"] = g["tournament_id"].map(bb_played).fillna(0).astype(int)
    g["played_without_ball_by_ball"] = g["played_matches"] - g["played_with_ball_by_ball"]
    g["ball_by_ball_coverage_pct_of_played"] = _div(
        100 * g["played_with_ball_by_ball"].astype(float), g["played_matches"].astype(float), 1
    )
    g["scorecard_matches"] = (
        g["tournament_id"]
        .map(
            S["batting"]
            .merge(fm[["match_id", "tournament_id"]], on="match_id")
            .groupby("tournament_id")["match_id"]
            .nunique()
        )
        .fillna(0)
        .astype(int)
    )
    g["standings_rows"] = (
        g["tournament_id"].map(S["standings"].groupby("tournament_id").size()).fillna(0).astype(int)
    )
    teams_played = pd.concat(
        [
            fm[["tournament_id", "team1_id"]].rename(columns={"team1_id": "t"}),
            fm[["tournament_id", "team2_id"]].rename(columns={"team2_id": "t"}),
        ]
    ).drop_duplicates()
    g["teams"] = g["tournament_id"].map(teams_played.groupby("tournament_id").size())
    g["teams_with_squad"] = (
        g["tournament_id"]
        .map(
            S["squads"][~S["squads"]["is_withdrawn"]].groupby("tournament_id")["team_id"].nunique()
        )
        .fillna(0)
        .astype(int)
    )
    g["has_player_of_tournament"] = g["tournament_id"].isin(
        S["awards"].query("award_scope == 'tournament'")["tournament_id"]
    )
    g["ball_by_ball_source"] = "Cricsheet (only free complete source; verified exhaustive)"
    g["phase_and_dot_ball_metrics_available"] = g["played_with_ball_by_ball"]
    return g.sort_values(["format", "year"]).reset_index(drop=True)


# --------------------------------------------------------------------------- orchestration
def _first_role(value) -> str | None:
    """playing_roles is a JSON list for ESPN rows and plain text for manual rows."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = str(value).strip()
    if text.startswith("["):
        try:
            roles = json.loads(text)
            return str(roles[0]) if roles else None
        except ValueError:
            return None
    return text or None


def fact_squads(S: dict[str, pd.DataFrame], fp: pd.DataFrame) -> pd.DataFrame:
    """Tournament squads, with age at the tournament and whether the player actually played for the team."""
    sq = S["squads"].copy()
    start = pd.to_datetime(
        S["tournaments"].set_index("tournament_id")["start_date"], errors="coerce"
    )
    dob = pd.to_datetime(sq["date_of_birth"], errors="coerce")
    sq["age_at_tournament"] = ((sq["tournament_id"].map(start) - dob).dt.days / 365.25).round(1)
    sq["playing_role"] = sq["playing_roles"].map(_first_role)
    played = (
        fp.groupby(["tournament_id", "team_id", "player_id"])
        .size()
        .rename("matches_played")
        .reset_index()
    )
    sq = sq.merge(played, on=["tournament_id", "team_id", "player_id"], how="left")
    sq["matches_played"] = sq["matches_played"].fillna(0).astype(int)
    sq["played_for_team"] = sq["matches_played"] > 0
    cols = [
        "tournament_id",
        "team_id",
        "player_id",
        "full_name",
        "role_code",
        "playing_role",
        "is_captain",
        "is_wicketkeeper",
        "batting_style",
        "bowling_style",
        "date_of_birth",
        "age_at_tournament",
        "is_overseas",
        "is_withdrawn",
        "source",
        "played_for_team",
        "matches_played",
    ]
    for c in cols:
        if c not in sq:
            sq[c] = None
    out = sq[cols].copy()
    out["full_name"] = out["full_name"].fillna(out["player_id"])
    for c in ("is_captain", "is_wicketkeeper", "is_overseas", "is_withdrawn"):
        out[c] = out[c].fillna(False).astype(bool)
    return out.sort_values(["tournament_id", "team_id", "full_name"]).reset_index(drop=True)


def build_gold(root: Path) -> dict[str, Any]:
    S = {
        n: read_silver(root, n)
        for n in [
            "tournaments",
            "teams",
            "matches",
            "innings",
            "deliveries",
            "players",
            "batting",
            "bowling",
            "fielding",
            "squads",
            "standings",
            "awards",
        ]
    }
    out: dict[str, pd.DataFrame] = {}
    out["dim_tournaments"] = dim_tournaments(S)
    out["dim_teams"] = dim_teams(S)
    out["dim_players"] = dim_players(S)
    out["dim_venues"] = dim_venues(S)
    out["dim_dates"] = dim_dates(S)
    out["fact_deliveries"] = fd = fact_deliveries(S)
    out["fact_innings"] = fi = fact_innings(S, fd)
    out["fact_matches"] = fm = fact_matches(S, fi, out["dim_venues"])
    out["fact_player_performances"] = fp = fact_player_performances(S, fm)
    out["fact_super_over_performances"] = fact_super_over_performances(S)
    out["fact_tournament_standings"] = fact_tournament_standings(S)
    out["fact_squads"] = fact_squads(S, fp)
    out["mart_batting"] = mart_batting(fp, True)
    out["mart_batting_career"] = mart_batting(fp, False)
    out["mart_bowling"] = mart_bowling(fp, True)
    out["mart_bowling_career"] = mart_bowling(fp, False)
    out["mart_team_performance"] = mart_team_performance(S, fm, fi)
    out["mart_tournament_summary"] = mart_tournament_summary(S, fm, fi)
    out["mart_data_coverage"] = mart_data_coverage(S, fm)
    return {name: _write(root, name, df) for name, df in out.items()}
