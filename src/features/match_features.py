# ruff: noqa: E501
"""Stage 11: pre-match feature engineering with a hard guarantee against temporal leakage.

Rules enforced here (and tested in tests/test_features.py):
1. Matches are processed in date order. A match's features are computed from state built **only from
   matches on strictly earlier dates**; a whole day is featurised before any of that day's results are
   added to the state, so two matches on the same day never see each other.
2. Nothing from the match itself (scores, winner, margin, player performances) is used. Only facts known
   before the first ball are used: who plays, venue, stage, toss, and prior history.
3. Rating/win-rate/run features are shrunk towards a prior so teams with little history are not read as
   extreme (cold start), and the amount of history is itself a feature.
4. Team order is assigned by a deterministic hash of the match id, so "team A" is not systematically
   the batting-first or home side and the label is not biased by source ordering.

Output: one row per match with symmetric A-minus-B difference features, the label (team A won) and the
first-innings target for the score model.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ELO_START = 1500.0
ELO_K = 30.0
FORM_WINDOW = 5
WIN_PRIOR = 5.0  # pseudo-matches at 50% (shrinks win rate for teams with little history)
RUN_PRIOR = 3.0  # pseudo-innings at the running format mean
H2H_PRIOR = 2.0
VENUE_PRIOR = 2.0
DEFAULT_FIRST_INNINGS = {"ODI": 250.0, "T20": 150.0, "Test": 300.0}  # only used before any history exists (round numbers, not fitted to the data)

DB = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "cricket_gold.duckdb"

FEATURES_WINNER = [
    "elo_diff",
    "win_rate_diff",
    "form_diff",
    "runs_for_diff",
    "runs_against_diff",
    "h2h_rate_a",
    "min_prior_matches",
    "venue_avg_first_innings",
    "is_knockout",
    "is_t20",
    "year",
    "toss_edge_a",
    "toss_field",
]
FEATURES_SCORE = [
    "bat_runs_for",
    "bowl_runs_against",
    "venue_avg_first_innings",
    "venue_prior_n",
    "format_avg_first_innings",
    "is_t20",
    "year",
    "bat_elo_diff",
]


FEATURES_SQUAD = ["xi_bat_avg_diff", "xi_bowl_econ_diff", "xi_experience_diff", "xi_knockout_exp_diff"]
FEATURES_WINNER_EXT = FEATURES_WINNER + FEATURES_SQUAD
BAT_PRIOR = 5.0  # pseudo-dismissals at the format's running batting average
BOWL_PRIOR_BALLS = 60.0  # pseudo-balls at the format's running economy


@dataclass
class _Player:
    runs: float = 0.0
    outs: int = 0
    conceded: float = 0.0
    balls: float = 0.0
    matches: int = 0
    knockouts: int = 0


@dataclass
class _Team:
    elo: float = ELO_START
    wins: int = 0
    matches: int = 0
    recent: deque = field(default_factory=lambda: deque(maxlen=FORM_WINDOW))
    runs_for: float = 0.0
    runs_against: float = 0.0
    run_innings: int = 0


@dataclass
class _Format:
    run_sum: float = 0.0
    run_n: int = 0
    first_sum: float = 0.0
    first_n: int = 0
    bat_runs: float = 0.0
    bat_outs: int = 0
    bowl_runs: float = 0.0
    bowl_balls: float = 0.0


def team_a_is_team1(match_id: str) -> bool:
    """Deterministic pseudo-random orientation (stable across runs and machines)."""
    return int(hashlib.md5(str(match_id).encode()).hexdigest(), 16) % 2 == 0


def load_matches(db: Path = DB) -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(
            "select match_id, tournament_id, format, year, match_date, is_knockout, venue_id, "
            "team1_id, team2_id, winner_id, toss_winner_id, toss_decision, is_completed, "
            "is_walkover, is_tie, is_dls, batting_first_team_id, batting_second_team_id, "
            "first_innings_runs, second_innings_runs, margin_type from gold.fact_matches"
        ).fetchdf()
    finally:
        con.close()


def _shrunk_rate(wins: float, n: float, prior: float = WIN_PRIOR) -> float:
    return (wins + 0.5 * prior) / (n + prior)


def _avg_runs(sum_runs: float, n: int, fmt_mean: float) -> float:
    return (sum_runs + RUN_PRIOR * fmt_mean) / (n + RUN_PRIOR)


def load_performances(db: Path = DB) -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(
            "select match_id, team_id, player_id, did_bat, did_bowl, runs, is_out, balls_bowled, "
            "runs_conceded, is_knockout from gold.fact_player_performances"
        ).fetchdf()
    finally:
        con.close()


def _xi_stats(fmt: str, players: list[str], pstate: dict, fm: _Format) -> tuple[float, float, float, float]:
    """Average career batting average / economy / experience of a side, from history only."""
    prior_avg = fm.bat_runs / fm.bat_outs if fm.bat_outs else 25.0
    prior_econ = 6.0 * fm.bowl_runs / fm.bowl_balls if fm.bowl_balls else 5.5
    bats, econs, exp, ko = [], [], [], []
    for pid in players:
        p = pstate[(fmt, pid)]
        bats.append((p.runs + BAT_PRIOR * prior_avg) / (p.outs + BAT_PRIOR))
        econs.append(
            6.0 * (p.conceded + BOWL_PRIOR_BALLS * prior_econ / 6.0) / (p.balls + BOWL_PRIOR_BALLS)
        )
        exp.append(p.matches)
        ko.append(p.knockouts)
    n = max(len(players), 1)
    return sum(bats) / n, sum(econs) / n, sum(exp) / n, sum(ko) / n


def build_match_features(
    matches: pd.DataFrame, return_state: bool = False, perf: pd.DataFrame | None = None
):
    """Return the feature table. ``matches`` needs the columns of :func:`load_matches`.

    With ``return_state=True`` also returns the Elo rating of every (format, team) *after* the last
    match, which is what a prediction for a future match should use."""
    m = matches.sort_values(["match_date", "match_id"]).reset_index(drop=True)
    teams: dict[tuple[str, str], _Team] = defaultdict(_Team)
    fmts: dict[str, _Format] = defaultdict(_Format)
    h2h: dict[tuple[str, str, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )  # (fmt, lo, hi) -> wins of lo, n
    venue: dict[tuple[str, str], list[float]] = defaultdict(
        lambda: [0.0, 0]
    )  # (fmt, venue) -> sum, n
    rows: list[dict] = []
    pstate: dict[tuple[str, str], _Player] = defaultdict(_Player)
    perf_by_match = {mid: g for mid, g in perf.groupby("match_id")} if perf is not None else {}

    for _date, day in m.groupby("match_date", sort=True):
        # ---- 1) featurise every match of the day from state that excludes the day itself
        for r in day.itertuples():
            fmt = r.format
            fm = fmts[fmt]
            a_first = team_a_is_team1(r.match_id)
            a, b = (r.team1_id, r.team2_id) if a_first else (r.team2_id, r.team1_id)
            ta, tb = teams[(fmt, a)], teams[(fmt, b)]
            fmt_mean = fm.run_sum / fm.run_n if fm.run_n else DEFAULT_FIRST_INNINGS[fmt]
            first_mean = fm.first_sum / fm.first_n if fm.first_n else DEFAULT_FIRST_INNINGS[fmt]

            def stats(t: _Team, fmt_mean=fmt_mean):
                return (
                    _shrunk_rate(t.wins, t.matches),
                    _shrunk_rate(sum(t.recent), len(t.recent)),
                    _avg_runs(t.runs_for, t.run_innings, fmt_mean),
                    _avg_runs(t.runs_against, t.run_innings, fmt_mean),
                )

            wr_a, fo_a, rf_a, ra_a = stats(ta)
            wr_b, fo_b, rf_b, ra_b = stats(tb)
            lo, hi = sorted((a, b))
            hw, hn = h2h[(fmt, lo, hi)]
            a_wins = hw if a == lo else hn - hw
            vs, vn = venue[(fmt, r.venue_id)]
            venue_avg = (vs + VENUE_PRIOR * first_mean) / (vn + VENUE_PRIOR)
            toss_edge = 0.0
            if pd.notna(r.toss_winner_id):
                toss_edge = 1.0 if r.toss_winner_id == a else -1.0
            bat_is_a = r.batting_first_team_id == a
            bat, bowl = (a, b) if bat_is_a else (b, a)
            tbat, tbowl = (ta, tb) if bat_is_a else (tb, ta)
            decided = bool(
                r.is_completed and not r.is_walkover and not r.is_tie and pd.notna(r.winner_id)
            )
            squad: dict[str, float] = {}
            if perf is not None:
                g = perf_by_match.get(r.match_id)
                if g is not None:
                    xa = _xi_stats(fmt, g.loc[g["team_id"] == a, "player_id"].tolist(), pstate, fm)
                    xb = _xi_stats(fmt, g.loc[g["team_id"] == b, "player_id"].tolist(), pstate, fm)
                else:  # no scorecard rows: neutral
                    xa = xb = (0.0, 0.0, 0.0, 0.0)
                squad = {
                    "xi_bat_avg_diff": xa[0] - xb[0],
                    "xi_bowl_econ_diff": xa[1] - xb[1],
                    "xi_experience_diff": xa[2] - xb[2],
                    "xi_knockout_exp_diff": xa[3] - xb[3],
                }
            rows.append(
                {
                    **squad,
                    "match_id": r.match_id,
                    "tournament_id": r.tournament_id,
                    "format": fmt,
                    "match_date": r.match_date,
                    "team_a_id": a,
                    "team_b_id": b,
                    "elo_a": ta.elo,
                    "elo_b": tb.elo,
                    "elo_diff": ta.elo - tb.elo,
                    "win_rate_diff": wr_a - wr_b,
                    "form_diff": fo_a - fo_b,
                    "runs_for_diff": rf_a - rf_b,
                    "runs_against_diff": ra_a - ra_b,
                    "h2h_rate_a": (a_wins + 0.5 * H2H_PRIOR) / (hn + H2H_PRIOR),
                    "min_prior_matches": min(ta.matches, tb.matches),
                    "venue_avg_first_innings": venue_avg,
                    "venue_prior_n": vn,
                    "is_knockout": int(bool(r.is_knockout)),
                    "is_t20": int(fmt == "T20"),
                    "year": int(r.year),
                    "toss_edge_a": toss_edge,
                    "toss_field": int(r.toss_decision == "field"),
                    # --- score model (batting-first side known after the toss)
                    "bat_team_id": bat,
                    "bat_runs_for": _avg_runs(tbat.runs_for, tbat.run_innings, fmt_mean),
                    "bowl_runs_against": _avg_runs(tbowl.runs_against, tbowl.run_innings, fmt_mean),
                    "format_avg_first_innings": first_mean,
                    "bat_elo_diff": tbat.elo - tbowl.elo,
                    # --- targets (never used as features)
                    "y_a_wins": float(r.winner_id == a) if decided else np.nan,
                    "y_first_innings_runs": float(r.first_innings_runs)
                    if pd.notna(r.first_innings_runs) and not r.is_dls
                    else np.nan,
                }
            )

        # ---- 2) only now fold the day's results into the state
        for r in day.itertuples():
            fmt = r.format
            fm = fmts[fmt]
            t1, t2 = teams[(fmt, r.team1_id)], teams[(fmt, r.team2_id)]
            decided = bool(
                r.is_completed and not r.is_walkover and not r.is_tie and pd.notna(r.winner_id)
            )
            # a completed Test draw counts as half a win for each side in the Elo rating (nothing else uses it:
            # win rates, form and head-to-head still count decided matches only)
            drawn = bool(
                r.is_completed
                and not decided
                and pd.isna(r.winner_id)
                and getattr(r, "margin_type", None) == "draw"
            )
            if drawn:
                e1 = 1.0 / (1.0 + 10 ** ((t2.elo - t1.elo) / 400.0))
                t1.elo += ELO_K * (0.5 - e1)
                t2.elo -= ELO_K * (0.5 - e1)
            if decided:
                w1 = 1.0 if r.winner_id == r.team1_id else 0.0
                e1 = 1.0 / (1.0 + 10 ** ((t2.elo - t1.elo) / 400.0))
                t1.elo += ELO_K * (w1 - e1)
                t2.elo -= ELO_K * (w1 - e1)
                for t, won in ((t1, w1), (t2, 1.0 - w1)):
                    t.wins += int(won)
                    t.matches += 1
                    t.recent.append(int(won))
                lo, hi = sorted((r.team1_id, r.team2_id))
                rec = h2h[(fmt, lo, hi)]
                rec[0] += int(r.winner_id == lo)
                rec[1] += 1
            if pd.notna(r.first_innings_runs) and pd.notna(r.second_innings_runs) and not r.is_dls:
                fr, sr = float(r.first_innings_runs), float(r.second_innings_runs)
                first_team = teams[(fmt, r.batting_first_team_id)]
                second_team = teams[(fmt, r.batting_second_team_id)]
                first_team.runs_for += fr
                first_team.runs_against += sr
                first_team.run_innings += 1
                second_team.runs_for += sr
                second_team.runs_against += fr
                second_team.run_innings += 1
                fm.run_sum += fr + sr
                fm.run_n += 2
                fm.first_sum += fr
                fm.first_n += 1
                v = venue[(fmt, r.venue_id)]
                v[0] += fr
                v[1] += 1
            g = perf_by_match.get(r.match_id)
            if g is not None:
                for pr in g.itertuples(index=False):
                    p = pstate[(fmt, pr.player_id)]
                    p.matches += 1
                    p.knockouts += int(bool(r.is_knockout))
                    if pr.did_bat and pd.notna(pr.runs):
                        p.runs += float(pr.runs)
                        p.outs += int(bool(pr.is_out)) if pd.notna(pr.is_out) else 0
                        fm.bat_runs += float(pr.runs)
                        fm.bat_outs += int(bool(pr.is_out)) if pd.notna(pr.is_out) else 0
                    if pr.did_bowl and pd.notna(pr.balls_bowled):
                        p.balls += float(pr.balls_bowled)
                        p.conceded += float(pr.runs_conceded)
                        fm.bowl_balls += float(pr.balls_bowled)
                        fm.bowl_runs += float(pr.runs_conceded)
    frame = pd.DataFrame(rows)
    if return_state:
        return frame, {k: v.elo for k, v in teams.items()}
    return frame


FEATURE_CATALOG = [
    (
        "elo_diff",
        "Elo rating of team A minus team B (per format, K=30, updated after decided matches; a Test draw counts as half a win)",
        "team history",
    ),
    (
        "win_rate_diff",
        "Shrunk win rate A minus B over all prior matches in the format",
        "team history",
    ),
    ("form_diff", "Shrunk win rate over each team's last 5 matches, A minus B", "team history"),
    (
        "runs_for_diff",
        "Average runs scored per innings (shrunk to format mean), A minus B",
        "team history",
    ),
    ("runs_against_diff", "Average runs conceded per innings (shrunk), A minus B", "team history"),
    ("h2h_rate_a", "Shrunk share of prior meetings (same format) won by A", "pair history"),
    (
        "min_prior_matches",
        "Fewer prior matches of the two teams; says how reliable the history is",
        "team history",
    ),
    (
        "venue_avg_first_innings",
        "Shrunk average first-innings score at the ground in prior matches",
        "venue history",
    ),
    ("is_knockout", "Match is a knockout stage", "known pre-match"),
    ("is_t20", "Format indicator", "known pre-match"),
    ("year", "Tournament year (era effect: scores trend upward)", "known pre-match"),
    ("toss_edge_a", "+1 A won toss, -1 B won, 0 unknown", "known at toss"),
    ("toss_field", "Toss winner chose to field", "known at toss"),
    (
        "bat_runs_for / bowl_runs_against",
        "Score model: batting side's average runs for and bowling side's runs against",
        "team history",
    ),
    (
        "bat_elo_diff",
        "Score model: Elo of the batting-first side minus the bowling side",
        "team history",
    ),
]


def write_catalog(root: Path) -> Path:
    lines = [
        "# Feature catalog (Stage 11)",
        "",
        "All features are computed from matches strictly before the match date (see "
        "`src/features/match_features.py`). Team A/B order is a deterministic hash of the match id.",
        "",
        "| Feature | Meaning | Source |",
        "|---|---|---|",
    ]
    lines += [f"| `{n}` | {d} | {s} |" for n, d, s in FEATURE_CATALOG]
    lines += [
        "",
        "## Deliberately excluded (would leak the outcome)",
        "",
        "* scores, margins, winner, player of the match, any in-match statistic;",
        "* player-level career tables built from the whole dataset (they include the match itself);",
        "* standings points of the tournament as a whole (final tables include future matches);",
        "* squads announced after the tournament start (unclear timing), so squad strength is not used.",
        "",
    ]
    out = root / "docs" / "feature_catalog.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
