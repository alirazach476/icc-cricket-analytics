# ruff: noqa: E501
"""Dashboard queries over the gold layer. All parameterised; none touch synthetic data except
``synthetic_conditions`` (which the UI labels as synthetic)."""

from __future__ import annotations

import re

import pandas as pd

from app.utils.database import PROJECT_ROOT, run


def formats() -> list[str]:
    """Formats present in the current database (World Cups: ODI and T20; Champions Trophy: ODI; Test: Test)."""
    order = {"ODI": 0, "T20": 1, "Test": 2}
    f = run("select distinct format from gold.dim_tournaments")["format"].tolist()
    return sorted(f, key=lambda x: order.get(x, 9)) or ["ODI"]


def tournaments() -> pd.DataFrame:
    return run(
        "select tournament_id, tournament_name, format, year, host_country, winner, runner_up, "
        "matches, runs_per_match, sixes, player_of_tournament from gold.mart_tournament_summary "
        "order by format, year"
    )


def overview() -> pd.DataFrame:
    return run(
        "select (select count(*) from gold.fact_matches) matches, "
        "(select count(*) from gold.dim_players) players, "
        "(select count(*) from gold.fact_deliveries) deliveries, "
        "(select count(*) from gold.dim_tournaments) tournaments, "
        "(select count(*) from gold.dim_venues) venues"
    )


def standings(tid: str) -> pd.DataFrame:
    return run(
        'select s.group_name as "group", s.position, t.team_name as team, s.matches_played as played, '
        "s.wins, s.losses, s.ties, s.no_results as nr, s.points, s.net_run_rate as nrr "
        "from gold.fact_tournament_standings s join gold.dim_teams t using (team_id) "
        "where s.tournament_id = ? order by s.group_name, s.position",
        (tid,),
    )


def tournament_of(mid: str) -> str | None:
    """Name of the tournament a match belongs to."""
    r = run("select tournament_name from gold.fact_matches where match_id = ?", (mid,))
    return None if r.empty else str(r["tournament_name"].iloc[0])


def matches_of(tid: str) -> pd.DataFrame:
    return run(
        "select m.match_id, m.match_date, m.stage, m.group_name, t1.team_name as team1, "
        "t2.team_name as team2, w.team_name as winner, m.margin_type, m.margin_value, "
        "v.venue_name as venue, m.has_ball_by_ball, m.ball_by_ball_gap_reason "
        "from gold.fact_matches m join gold.dim_teams t1 on t1.team_id = m.team1_id "
        "join gold.dim_teams t2 on t2.team_id = m.team2_id "
        "left join gold.dim_teams w on w.team_id = m.winner_id "
        "left join gold.dim_venues v on v.venue_id = m.venue_id "
        "where m.tournament_id = ? order by m.match_date, m.match_id",
        (tid,),
    )


def top_batters(tid: str, n: int = 10) -> pd.DataFrame:
    return run(
        "select p.full_name as player, b.runs, b.innings, b.average, b.strike_rate, b.hundreds, b.fifties "
        "from gold.mart_batting b join gold.dim_players p using (player_id) "
        "where b.tournament_id = ? order by b.runs desc limit ?",
        (tid, n),
    )


def top_bowlers(tid: str, n: int = 10) -> pd.DataFrame:
    return run(
        "select p.full_name as player, b.wickets, b.matches, b.economy, b.average, b.best_figures "
        "from gold.mart_bowling b join gold.dim_players p using (player_id) "
        "where b.tournament_id = ? order by b.wickets desc, b.economy limit ?",
        (tid, n),
    )


def match_header(mid: str) -> pd.DataFrame:
    return run(
        "select m.*, t1.team_name as team1, t2.team_name as team2, w.team_name as winner, "
        "v.venue_name as venue, v.city as venue_city, pm.full_name as player_of_match "
        "from gold.fact_matches m join gold.dim_teams t1 on t1.team_id = m.team1_id "
        "join gold.dim_teams t2 on t2.team_id = m.team2_id "
        "left join gold.dim_teams w on w.team_id = m.winner_id "
        "left join gold.dim_venues v on v.venue_id = m.venue_id "
        "left join gold.dim_players pm on pm.player_id = m.player_of_match_id where m.match_id = ?",
        (mid,),
    )


def match_innings(mid: str) -> pd.DataFrame:
    return run(
        "select i.innings_number as innings, t.team_name as batting, i.total_runs as runs, i.wickets, "
        "i.overs, i.run_rate, i.extras, i.is_super_over as super_over "
        "from gold.fact_innings i join gold.dim_teams t on t.team_id = i.batting_team_id "
        "where i.match_id = ? order by i.innings_number",
        (mid,),
    )


def match_batting(mid: str) -> pd.DataFrame:
    return run(
        "select t.team_name as team, f.batting_innings as inn, f.batting_position as pos, p.full_name as batter, f.runs, "
        "f.balls_faced as balls, f.fours, f.sixes, f.strike_rate as sr, f.dismissal_type as dismissal "
        "from gold.fact_player_performances f join gold.dim_players p using (player_id) "
        "join gold.dim_teams t on t.team_id = f.team_id where f.match_id = ? and f.did_bat "
        "order by t.team_name, f.batting_innings, f.batting_position",
        (mid,),
    )


def match_bowling(mid: str) -> pd.DataFrame:
    return run(
        "select t.team_name as team, p.full_name as bowler, cast(f.balls_bowled // 6 as double) + (f.balls_bowled % 6) / 10.0 as overs, f.maidens as m, "
        "f.runs_conceded as runs, f.wickets as w, f.economy as econ "
        "from gold.fact_player_performances f join gold.dim_players p using (player_id) "
        "join gold.dim_teams t on t.team_id = f.team_id where f.match_id = ? and f.did_bowl "
        "order by t.team_name, f.wickets desc",
        (mid,),
    )


def match_overs(mid: str) -> pd.DataFrame:
    return run(
        "select innings_number as innings, over_number as over, sum(total_runs) as runs, "
        "count(*) filter (where is_wicket) as wickets, max(cumulative_runs) as cumulative_runs "
        "from gold.fact_deliveries where match_id = ? and not is_super_over "
        "group by 1, 2 order by 1, 2",
        (mid,),
    )


def ball_matches() -> pd.DataFrame:
    return run(
        "select m.match_id, m.tournament_id, m.match_date, t1.team_name || ' v ' || t2.team_name as fixture "
        "from gold.fact_matches m join gold.dim_teams t1 on t1.team_id = m.team1_id "
        "join gold.dim_teams t2 on t2.team_id = m.team2_id where m.has_ball_by_ball "
        "order by m.match_date desc, m.match_id"
    )


def deliveries(mid: str) -> pd.DataFrame:
    return run(
        "select d.innings_number as innings, d.over_number as over, d.ball_number as ball, "
        "d.phase, b.full_name as batter, w.full_name as bowler, d.batter_runs as runs, "
        "d.extra_runs as extras, d.total_runs, d.is_wicket as wicket, d.dismissal_type "
        "from gold.fact_deliveries d join gold.dim_players b on b.player_id = d.batter_id "
        "join gold.dim_players w on w.player_id = d.bowler_id where d.match_id = ? "
        "order by d.innings_number, d.delivery_sequence",
        (mid,),
    )


def player_search(text: str, limit: int = 50) -> pd.DataFrame:
    return run(
        "select player_id, full_name from gold.dim_players where lower(full_name) like ? "
        "order by full_name limit ?",
        (f"%{text.lower()}%", limit),
    )


def player_batting_career(pid: str) -> pd.DataFrame:
    return run(
        "select format, matches, innings, runs, highest_score as hs, average, strike_rate as sr, "
        "hundreds, fifties, fours, sixes from gold.mart_batting_career where player_id = ?",
        (pid,),
    )


def player_bowling_career(pid: str) -> pd.DataFrame:
    return run(
        "select format, matches, wickets, economy, average, strike_rate as sr, best_figures, "
        "five_wicket_hauls as five_w from gold.mart_bowling_career where player_id = ?",
        (pid,),
    )


def player_by_tournament(pid: str) -> pd.DataFrame:
    return run(
        "select t.format || ' ' || t.year as tournament, b.runs, b.innings, b.average, b.strike_rate as sr, "
        "coalesce(w.wickets, 0) as wickets, w.economy "
        "from gold.mart_batting b join gold.dim_tournaments t using (tournament_id) "
        "left join gold.mart_bowling w on w.player_id = b.player_id and w.tournament_id = b.tournament_id "
        "where b.player_id = ? order by t.year, t.format",
        (pid,),
    )


def player_phases(pid: str) -> pd.DataFrame:
    return run(
        "select format, phase, count(*) filter (where not is_wide) as balls, sum(batter_runs) as runs, "
        "round(100.0 * sum(batter_runs) / nullif(count(*) filter (where not is_wide), 0), 1) as strike_rate "
        "from gold.fact_deliveries where batter_id = ? and not is_super_over "
        "and phase in ('powerplay','middle','death') group by 1, 2 order by 1, 2",
        (pid,),
    )


def teams() -> pd.DataFrame:
    return run("select team_id, team_name from gold.dim_teams order by team_name")


def team_record(team_id: str) -> pd.DataFrame:
    return run(
        "select t.format || ' ' || t.year as tournament, p.matches, p.wins, p.losses, p.win_pct, "
        "p.furthest_stage as furthest, p.is_champion as champion "
        "from gold.mart_team_performance p join gold.dim_tournaments t using (tournament_id) "
        "where p.team_id = ? order by t.year, t.format",
        (team_id,),
    )


def team_head_to_head(team_id: str) -> pd.DataFrame:
    return run(
        "select o.team_name as opponent, m.format, count(*) as matches, "
        "count(*) filter (where m.winner_id = ?) as wins, "
        "count(*) filter (where m.winner_id is not null and m.winner_id <> ?) as losses "
        "from gold.fact_matches m join gold.dim_teams o "
        "on o.team_id = case when m.team1_id = ? then m.team2_id else m.team1_id end "
        "where ? in (m.team1_id, m.team2_id) group by 1, 2 order by matches desc, opponent",
        (team_id, team_id, team_id, team_id),
    )


def coverage() -> pd.DataFrame:
    return run(
        "select tournament_name, format, year, played_matches, played_with_ball_by_ball as with_bbb, "
        "ball_by_ball_coverage_pct_of_played as coverage_pct, standings_rows, teams, teams_with_squad "
        "from gold.mart_data_coverage order by format, year"
    )


def gap_reasons() -> pd.DataFrame:
    return run(
        "select coalesce(ball_by_ball_gap_reason, 'has ball-by-ball') as status, count(*) as matches "
        "from gold.fact_matches group by 1 order by 2 desc"
    )


def synthetic_conditions(mid: str) -> pd.DataFrame:
    """SYNTHETIC placeholders (see docs/synthetic_data.md); callers must label them as such."""
    try:
        return run("select * from gold.synthetic_match_conditions where match_id = ?", (mid,))
    except Exception:  # noqa: BLE001 - table may not be loaded
        return pd.DataFrame()


def parse_library() -> list[dict[str, str]]:
    """The Stage 8 SQL library, for the Records page."""
    text = (PROJECT_ROOT / "sql" / "analytics" / "queries.sql").read_text(encoding="utf-8")
    out = []
    for block in re.split(r"(?m)^-- name:\s*", text)[1:]:
        name, _, rest = block.partition("\n")
        meta = dict(re.findall(r"(?m)^-- (group|question):\s*(.+)$", rest))
        sql = (
            "\n".join(ln for ln in rest.splitlines() if not ln.startswith("-- "))
            .strip()
            .rstrip(";")
        )
        out.append(
            {
                "name": name.strip(),
                "group": meta.get("group", ""),
                "question": meta.get("question", ""),
                "sql": sql,
            }
        )
    return out
