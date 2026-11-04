"""Player identity resolution: Cricsheet names -> ESPN player ids, per match (Stage 4).

Ball-by-ball (Cricsheet) names players like ``"JM Bairstow"``; scorecards (ESPN) use ESPN ids with a
full name (``"Jonny Bairstow"``) and a batting name (``"JM Bairstow"``). Names alone are ambiguous
across the whole dataset, so resolution is **per match, against that match's own roster**: a name can
only resolve to someone who actually appeared in that match. Stages run strictest first, and a stage
that finds more than one candidate resolves nothing (no guessing). A shared surname alone is never
enough: it was tried and rejected because it mis-assigned 7 of 8 cases when checked against scorecards.

Methods, in order of confidence:
1. ``batting_name``  exact (normalised) match with the ESPN batting name
2. ``full_name``     exact match with the ESPN full name
3. ``token_set``    same words in a different order ("Waseem Muhammad" ~ "Muhammad Waseem")
   ``initials``      same surname and the initials agree ("JM Bairstow" ~ "Jonathan Mark Bairstow")
4. ``fuzzy``         one clearly best similarity >= 0.88 and 0.05 ahead of the runner-up
5. ``elimination``   (match level) exactly one unresolved name and exactly one unmatched roster
                     player who took part remain for that team, so they must be the same person
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

METHODS = ("batting_name", "full_name", "token_set", "initials", "fuzzy", "elimination")


def norm(name: str | None) -> str:
    """Lower-case, accent-free, punctuation-free, single-spaced."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def cricsheet_slug(name: str) -> str:
    """The id the database loader derived from a Cricsheet name (``cricsheet_<slug>``)."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


@dataclass(frozen=True)
class RosterPlayer:
    player_id: str
    full_name: str
    batting_name: str
    team_id: str | None = None


def _surname(name: str) -> str:
    parts = norm(name).split()
    return parts[-1] if parts else ""


def _initials(name: str) -> str:
    """Initials of all given names (everything before the surname)."""
    parts = norm(name).split()
    return "".join(p[0] for p in parts[:-1])


def _cricsheet_initials(name: str) -> str:
    """For 'JM Bairstow' the leading all-caps token holds the initials; else first letters."""
    raw = name.split()
    if len(raw) >= 2 and raw[0].isupper() and len(raw[0]) <= 4:
        return raw[0].lower()
    return _initials(name)


def resolve_name(name: str, roster: list[RosterPlayer]) -> tuple[str | None, str | None]:
    """Return ``(player_id, method)`` or ``(None, None)`` when no single safe match exists."""
    n = norm(name)
    if not n or not roster:
        return None, None

    for method, key in (
        ("batting_name", lambda p: norm(p.batting_name)),
        ("full_name", lambda p: norm(p.full_name)),
    ):
        hits = [p for p in roster if key(p) == n]
        if len(hits) == 1:
            return hits[0].player_id, method
        if len(hits) > 1:
            return None, None  # ambiguous even on an exact name: refuse

    tokens = sorted(n.split())
    hits = [
        p
        for p in roster
        if sorted(norm(p.full_name).split()) == tokens
        or sorted(norm(p.batting_name).split()) == tokens
    ]
    if len(hits) == 1:
        return hits[0].player_id, "token_set"
    if len(hits) > 1:
        return None, None

    sur = _surname(name)
    same_surname = [
        p for p in roster if _surname(p.full_name) == sur or _surname(p.batting_name) == sur
    ]
    ini = _cricsheet_initials(name)
    if ini:
        hits = [
            p
            for p in same_surname
            if (_initials(p.full_name) and _initials(p.full_name).startswith(ini))
            or (_initials(p.batting_name) and _initials(p.batting_name).startswith(ini))
            or ini.startswith(_initials(p.full_name) or "\0")
        ]
        if len(hits) == 1:
            return hits[0].player_id, "initials"
        if len(hits) > 1:
            return None, None
    if same_surname and not ini:
        return (
            None,
            None,
        )  # a shared surname alone is never enough (e.g. PWH de Silva is not Dhananjaya de Silva)

    scored = sorted(
        (
            (
                max(
                    SequenceMatcher(None, n, norm(p.batting_name)).ratio(),
                    SequenceMatcher(None, n, norm(p.full_name)).ratio(),
                ),
                p,
            )
            for p in roster
        ),
        key=lambda t: -t[0],
    )
    if (
        scored
        and scored[0][0] >= 0.88
        and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.05)
    ):
        return scored[0][1].player_id, "fuzzy"
    return None, None


NAME_COLUMNS = ("batter_id", "non_striker_id", "bowler_id", "dismissed_player_id", "fielder_id")


def build_identity_map(deliveries, players, batting, bowling, fielding, innings=None):
    """Resolve every name used in each match's deliveries against that match's scorecard roster.

    Returns ``(map_df, summary)``. ``map_df`` has one row per (match_id, name) with the resolved ESPN
    id (or null) and the method; it is the auditable record of every identity decision.
    """
    import pandas as pd

    names = {}
    for col in NAME_COLUMNS:
        sub = deliveries[["match_id", col]].dropna().rename(columns={col: "name"})
        sub["role"] = col
        names[col] = sub
    used = pd.concat(names.values())
    counts = used.groupby(["match_id", "name"]).size().rename("deliveries").reset_index()
    roles = (
        used.groupby(["match_id", "name"])["role"]
        .agg(lambda s: ",".join(sorted(set(s))))
        .reset_index()
    )
    used = counts.merge(roles, on=["match_id", "name"])

    info = players.drop_duplicates(["match_id", "player_id"])[
        ["match_id", "player_id", "full_name", "batting_name"]
    ]
    team = pd.concat(
        [
            batting[["match_id", "player_id", "team_id"]],
            bowling[["match_id", "player_id", "team_id"]],
            fielding[["match_id", "player_id", "team_id"]],
        ]
    ).drop_duplicates(["match_id", "player_id"])
    roster_df = info.merge(team, on=["match_id", "player_id"], how="outer")
    roster_df["full_name"] = roster_df["full_name"].fillna("")
    roster_df["batting_name"] = roster_df["batting_name"].fillna(roster_df["full_name"])
    rosters = {
        mid: [
            RosterPlayer(r.player_id, r.full_name, r.batting_name, r.team_id)
            for r in g.itertuples()
        ]
        for mid, g in roster_df.groupby("match_id")
    }

    rows = []
    for r in used.itertuples():
        pid, method = resolve_name(r.name, rosters.get(r.match_id, []))
        rows.append(
            {
                "match_id": r.match_id,
                "source_name": r.name,
                "source_id": f"cricsheet_{cricsheet_slug(r.name)}",
                "resolved_player_id": pid,
                "method": method,
                "deliveries": r.deliveries,
                "roles": r.role if hasattr(r, "role") else r.roles,
            }
        )
    out = pd.DataFrame(rows)
    if innings is not None:
        out = _eliminate(out, deliveries, innings, batting, bowling, fielding, rosters)
    resolved = out["resolved_player_id"].notna()
    summary = {
        "names_total": int(len(out)),
        "names_resolved": int(resolved.sum()),
        "names_resolved_pct": round(100 * resolved.mean(), 2),
        "deliveries_total": int(out["deliveries"].sum()),
        "deliveries_resolved_pct": round(
            100 * out.loc[resolved, "deliveries"].sum() / out["deliveries"].sum(), 2
        ),
        "by_method": out.loc[resolved, "method"].value_counts().to_dict(),
    }
    return out, summary


_BATTING_ROLES = {"batter_id", "non_striker_id", "dismissed_player_id"}


def _eliminate(out, deliveries, innings, batting, bowling, fielding, rosters):
    """Resolve the last unmatched name of a team in a match when exactly one player is left."""

    team_of = innings.set_index(["match_id", "innings_number"])[
        ["batting_team_id", "bowling_team_id"]
    ]
    unresolved = out[out["resolved_player_id"].isna()]
    if unresolved.empty:
        return out

    # team of each (match, name): batting team for batting roles, bowling team for bowling roles.
    votes = {}
    for col in NAME_COLUMNS:
        sub = deliveries[["match_id", "innings_number", col]].dropna().drop_duplicates()
        for r in sub.itertuples(index=False):
            key = (r.match_id, int(r.innings_number))
            if key not in team_of.index:
                continue
            row = team_of.loc[key]
            team = row["batting_team_id"] if col in _BATTING_ROLES else row["bowling_team_id"]
            votes.setdefault((r.match_id, getattr(r, col)), set()).add(team)

    took_part = {}
    did_bat = batting[batting["runs"].notna() | batting["balls_faced"].notna()]
    for frame in (did_bat, bowling, fielding):
        for r in frame[["match_id", "player_id", "team_id"]].itertuples(index=False):
            took_part.setdefault((r.match_id, r.team_id), set()).add(r.player_id)

    resolved_ids = (
        out[out["resolved_player_id"].notna()]
        .groupby("match_id")["resolved_player_id"]
        .agg(set)
        .to_dict()
    )
    pending = {}
    for r in unresolved.itertuples():
        teams = votes.get((r.match_id, r.source_name), set())
        if len(teams) == 1:
            pending.setdefault((r.match_id, next(iter(teams))), []).append(r.Index)

    for (mid, team), idxs in pending.items():
        free = took_part.get((mid, team), set()) - resolved_ids.get(mid, set())
        if len(idxs) == 1 and len(free) == 1:
            out.loc[idxs[0], "resolved_player_id"] = next(iter(free))
            out.loc[idxs[0], "method"] = "elimination"
    return out
