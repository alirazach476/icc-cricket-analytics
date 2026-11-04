# ruff: noqa: E501
"""ICC Men's Cricket World Cup 2027 (South Africa, Zimbabwe, Namibia): schedule, venues, teams, qualification.

The tournament has not been played, so there are no results. Everything here is published information:

* the official ICC fixture list (``config/wc2027_icc_fixtures.csv``, copied from icc-cricket.com),
* ESPNcricinfo's schedule (fetched with the project's polite collector, cached) as an independent second source,
* venue capacities and the qualification state from Wikipedia (pages named in the sources table),
* the project's own World Cup data for each team's and ground's history.

Each fixture says whether the two schedule sources agree. Qualification is still running (the qualifier is in
Feb-Mar 2027), so ``config``-level facts below carry the date they were checked and will change.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "competitions" / "wc27"
RAW = ROOT / "data" / "raw" / "competitions" / "espn" / "WC_M_2027"
WAREHOUSE = ROOT / "data" / "warehouse" / "cricket_gold_wc27.duckdb"
ESPN_SERIES = "https://www.espncricinfo.com/series/icc-cricket-world-cup-2027-28-1545817"
CHECKED = "2026-11-04"

GROUP_A = ["India", "Australia", "Pakistan", "Afghanistan", "Zimbabwe", "Qualifier A"]
GROUP_B = ["New Zealand", "South Africa", "Sri Lanka", "England", "Bangladesh", "Qualifier B"]
REAL = (set(GROUP_A) | set(GROUP_B)) - {"Qualifier A", "Qualifier B"}
SEEDS = {
    "A1": "India",
    "A2": "Australia",
    "A3": "Pakistan",
    "AB4": "England",
    "B1": "New Zealand",
    "B2": "South Africa",
    "B3": "Sri Lanka",
}

# city as printed by the ICC -> (ground, country, capacity listed on Wikipedia, approximate latitude, longitude, ESPN city spelling)
VENUES = {
    "Cape Town": ("Newlands Cricket Ground", "South Africa", 25000, -33.9728, 18.4686, "Cape Town"),
    "Johannesburg": ("Wanderers Stadium", "South Africa", 34000, -26.1317, 28.0600, "Johannesburg"),
    "Tshwane": (
        "SuperSport Park (Centurion)",
        "South Africa",
        22000,
        -25.8586,
        28.2124,
        "Centurion",
    ),
    "Durban": ("Kingsmead Cricket Ground", "South Africa", 25000, -29.8505, 31.0292, "Durban"),
    "Gqeberha": ("St George's Park", "South Africa", 19000, -33.9358, 25.6020, "Gqeberha"),
    "Bloemfontein": ("Mangaung Oval", "South Africa", 20000, -29.1189, 26.2127, "Bloemfontein"),
    "Paarl": ("Boland Park", "South Africa", 10000, -33.7246, 18.9748, "Paarl"),
    "KuGompo City": ("Buffalo Park", "South Africa", 16000, -32.9970, 27.9040, "KuGumpo City"),
    "Harare": ("Harare Sports Club", "Zimbabwe", 10000, -17.8042, 31.0482, "Harare"),
    "Bulawayo": ("Queens Sports Club", "Zimbabwe", 12500, -20.1600, 28.5890, "Bulawayo"),
    "Victoria Falls": (
        "Mosi-oa-Tunya International Cricket Stadium",
        "Zimbabwe",
        10000,
        -17.9437,
        25.8326,
        "Victoria Falls",
    ),
    "Windhoek": ("Namibia Cricket Ground", "Namibia", 7000, -22.5700, 17.0830, "Windhoek"),
}
# keyword that finds the same ground in the World Cup data (2003-2023)
HISTORY_KEY = {
    "Cape Town": "newlands",
    "Johannesburg": "wanderers",
    "Tshwane": "centurion",
    "Durban": "kingsmead",
    "Gqeberha": "st george",
    "Bloemfontein": "goodyear park",  # Mangaung Oval was called Goodyear Park at the 2003 World Cup
    "Paarl": "boland",
    "KuGompo City": "buffalo park",
    "Harare": "harare sports",
    "Bulawayo": "queens sports",
    "Victoria Falls": "mosi",
    "Windhoek": "namibia cricket",
}

PHASES = [
    (
        "Super Series",
        "Three-team round robin in Windhoek between three of the four qualifiers; the winner takes the last group-stage place.",
        "2027-10-02",
        "2027-10-06",
        3,
    ),
    (
        "Group Stage",
        "12 teams in two groups of six, each side plays the other five. Top three in each group plus the best fourth-placed team go to the Super 7.",
        "2027-10-07",
        "2027-10-24",
        30,
    ),
    (
        "Super 7",
        "Seven teams, no points carried over, each plays the other six once.",
        "2027-10-25",
        "2027-11-14",
        21,
    ),
    (
        "Semi-finals",
        "1st v 4th and 2nd v 3rd of the Super 7, each with a reserve day.",
        "2027-11-17",
        "2027-11-18",
        2,
    ),
    (
        "Final",
        "Wanderers, Johannesburg, with a reserve day on 22 November.",
        "2027-11-21",
        "2027-11-21",
        1,
    ),
]

SOURCES = [
    (
        "ICC fixture list",
        "https://www.icc-cricket.com/tournaments/icc-cricket-world-cup-2027/news/fixture-schedule-announced-for-icc-men-s-cricket-world-cup-2027",
        "official",
        "all 57 fixtures, groups, format, host cities",
    ),
    (
        "ICC venues and brand announcement",
        "https://www.icc-cricket.com/news/men-s-cricket-world-cup-2027-venues-and-brand-revealed",
        "official",
        "venues and logo",
    ),
    (
        "ESPNcricinfo series schedule",
        ESPN_SERIES + "/match-schedule-fixtures-and-results",
        "reference",
        "independent copy of the 57 fixtures (dates, grounds, teams)",
    ),
    (
        "Wikipedia: 2027 Cricket World Cup",
        "https://en.wikipedia.org/wiki/2027_Cricket_World_Cup",
        "reference",
        "venue capacities, format summary, hosts",
    ),
    (
        "Wikipedia: 2027 Cricket World Cup qualification",
        "https://en.wikipedia.org/wiki/2027_Cricket_World_Cup_qualification",
        "reference",
        "who has qualified and who is still to be decided",
    ),
]

QUALIFICATION = [
    (
        "Hosts",
        "South Africa and Zimbabwe qualified as full-member co-hosts.",
        "2021-11-16",
        "confirmed",
        "South Africa; Zimbabwe",
    ),
    (
        "ODI rankings",
        "The top eight ranked teams, excluding the hosts, at the cut-off of 30 September 2026.",
        "2026-09-30",
        "confirmed",
        "India; Australia; Pakistan; Afghanistan; New Zealand; Sri Lanka; England; Bangladesh",
    ),
    (
        "Qualifier: ranked teams",
        "The next two teams in the rankings go straight into the qualifier.",
        "2026-09-30",
        "confirmed",
        "Ireland; West Indies",
    ),
    (
        "Qualifier: League 2",
        "The top four of ICC Men's Cricket World Cup League 2 go to the qualifier. Three are decided; Oman and Namibia were level for the fourth place on 2 Nov 2026.",
        "2026-11-02",
        "in progress",
        "Netherlands; Scotland; United States; fourth place to be decided",
    ),
    (
        "Qualifier play-off",
        "Four teams from the lower leagues earn the last four qualifier places (4 to 22 Dec 2026): Canada, Nepal, UAE, the fourth League 2 side, Jersey, Kuwait, Italy and Uganda are in contention.",
        "2026-12-04",
        "not started",
        "to be decided",
    ),
    (
        "Cricket World Cup Qualifier",
        "Ten teams; the top four reach the World Cup. Played in late Feb to late March 2027 (sources give 22 Feb-23 Mar and 26 Feb-21 Mar), in South Africa and Namibia. Namibia, as co-host, is not guaranteed a place.",
        "2027-02-22",
        "not started",
        "to be decided",
    ),
    (
        "Super Series",
        "The qualifier winner goes straight to the group stage; the other three play the Super Series in Windhoek (2, 4 and 6 Oct 2027) and the winner takes the last group place.",
        "2027-10-02",
        "not started",
        "to be decided",
    ),
]


def _espn_schedule() -> pd.DataFrame:
    from src.collectors.base_collector import BaseCollector
    from src.parsers.match_list_parser import parse_match_schedule_html

    path = RAW / "schedule.html"
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        res = BaseCollector().fetch_html(ESPN_SERIES + "/match-schedule-fixtures-and-results")
        if not res.ok or not res.content:
            return pd.DataFrame()
        path.write_text(res.content, encoding="utf-8")
    parsed = parse_match_schedule_html(
        path.read_text(encoding="utf-8"), tournament_id="WC_M_2027", source_url=ESPN_SERIES
    )
    return pd.DataFrame(parsed["matches"])


def build_schedule() -> pd.DataFrame:
    icc = pd.read_csv(ROOT / "config" / "wc2027_icc_fixtures.csv", dtype=str, keep_default_na=False)
    espn = _espn_schedule()
    if len(espn):
        rev = {v[5]: k for k, v in VENUES.items()}
        espn["city"] = espn["city"].map(lambda c: rev.get(c, c))
        espn = espn.sort_values(["match_date", "match_id"]).reset_index(drop=True)
    rows = []
    for i, r in icc.iterrows():
        e = espn.iloc[i] if len(espn) == len(icc) else None
        t1, t2 = r["team1"], r["team2"] or None
        teams = {t for t in (t1, t2) if t}
        grp = "A" if teams & set(GROUP_A) else "B" if teams & set(GROUP_B) else None
        agree = None
        if e is not None:
            known = {x for x in (e["team1_name"], e["team2_name"]) if x}
            ok_teams = known <= teams  # ESPN leaves the unknown qualifier blank
            agree = bool(str(e["match_date"]) == r["date"] and e["city"] == r["city"] and ok_teams)
        v = VENUES[r["city"]]
        d = date.fromisoformat(r["date"])
        rows.append(
            {
                "match_no": int(r["match_no"]),
                "date": d,
                "weekday": d.strftime("%A"),
                "phase": r["phase"],
                "group": grp if r["phase"] == "Group Stage" else None,
                "team1": t1,
                "team2": t2,
                "team1_seed": SEEDS.get(t1),
                "team2_seed": SEEDS.get(t2) if t2 else None,
                "teams_known": t1 in REAL and t2 in REAL,
                "ground": v[0],
                "city": r["city"],
                "country": v[1],
                "reserve_day": {"Semi-final": "yes (next day)", "Final": "yes (22 Nov 2027)"}.get(
                    r["phase"], "no"
                ),
                "espn_match_id": None if e is None else str(e["match_id"]),
                "sources_agree": agree,
            }
        )
    out = pd.DataFrame(rows)
    return out


def _wc_history() -> tuple[pd.DataFrame, pd.DataFrame]:
    db = ROOT / "data" / "warehouse" / "cricket_gold.duckdb"
    con = duckdb.connect(str(db), read_only=True)
    try:
        teams = con.execute(
            """
            with m as (select tournament_id, year, team1_name t, winner_name w from gold.fact_matches where format = 'ODI'
                       union all select tournament_id, year, team2_name, winner_name from gold.fact_matches where format = 'ODI')
            select t team, count(distinct year) editions, count(*) matches, count(*) filter (where w = t) wins
            from m group by t
            """
        ).fetchdf()
        titles = con.execute(
            "select winner team, count(*) titles from gold.mart_tournament_summary where format = 'ODI' and winner is not null group by winner"
        ).fetchdf()
        finals = con.execute(
            "select runner_up team, count(*) finals_lost from gold.mart_tournament_summary where format = 'ODI' and runner_up is not null group by runner_up"
        ).fetchdf()
        teams = (
            teams.merge(titles, on="team", how="left")
            .merge(finals, on="team", how="left")
            .fillna({"titles": 0, "finals_lost": 0})
        )
        hist = []
        for city, key in HISTORY_KEY.items():
            r = (
                con.execute(
                    """
                select count(distinct m.match_id) matches, avg(m.first_innings_runs) avg_first_innings,
                       avg(case when m.won_by_batting_first then 1.0 else 0.0 end) filter (where m.winner_id is not null) bat_first_win
                from gold.fact_matches m join gold.dim_venues v using (venue_id)
                where m.format = 'ODI' and lower(v.venue_name) like ?
                """,
                    [f"%{key}%"],
                )
                .fetchdf()
                .iloc[0]
            )
            hist.append(
                {
                    "city": city,
                    "wc_matches": int(r["matches"]),
                    "avg_first_innings": None
                    if pd.isna(r["avg_first_innings"])
                    else round(float(r["avg_first_innings"]), 1),
                    "bat_first_win_pct": None
                    if pd.isna(r["bat_first_win"])
                    else round(100 * float(r["bat_first_win"]), 1),
                }
            )
        return teams, pd.DataFrame(hist)
    finally:
        con.close()


def build_all() -> dict:
    schedule = build_schedule()
    wc_teams, hist = _wc_history()
    # venues
    vrows = []
    for city, v in VENUES.items():
        s = schedule[schedule["city"] == city]
        h = hist[hist["city"] == city].iloc[0]
        vrows.append(
            {
                "ground": v[0],
                "city": city,
                "country": v[1],
                "capacity": v[2],
                "latitude": v[3],
                "longitude": v[4],
                "matches": len(s),
                "first_match": s["date"].min(),
                "last_match": s["date"].max(),
                "phases": ", ".join(
                    sorted(
                        s["phase"].unique(),
                        key=["Super Series", "Group Stage", "Super 7", "Semi-final", "Final"].index,
                    )
                ),
                "hosts_semi_or_final": bool(s["phase"].isin(["Semi-final", "Final"]).any()),
                "wc_matches_2003_2023": int(h["wc_matches"]),
                "avg_first_innings": h["avg_first_innings"],
                "bat_first_win_pct": h["bat_first_win_pct"],
            }
        )
    venues = pd.DataFrame(vrows).sort_values("matches", ascending=False).reset_index(drop=True)
    # teams
    status = {
        t: ("host" if t in ("South Africa", "Zimbabwe") else "qualified by ODI ranking")
        for t in GROUP_A + GROUP_B
        if not t.startswith("Qualifier")
    }
    trows = []
    for grp, names in (("A", GROUP_A), ("B", GROUP_B)):
        for t in names:
            h = wc_teams[wc_teams["team"] == t]
            seed = next((k for k, v in SEEDS.items() if v == t), None)
            trows.append(
                {
                    "team": t,
                    "group": grp,
                    "status": status.get(t, "to be decided by the qualifier"),
                    "confirmed": not t.startswith("Qualifier"),
                    "super7_seed": seed,
                    "wc_editions_2003_2023": int(h["editions"].iloc[0]) if len(h) else 0,
                    "wc_matches": int(h["matches"].iloc[0]) if len(h) else 0,
                    "wc_wins": int(h["wins"].iloc[0]) if len(h) else 0,
                    "wc_titles": int(h["titles"].iloc[0]) if len(h) else 0,
                    "wc_finals_lost": int(h["finals_lost"].iloc[0]) if len(h) else 0,
                    "match_count_2027": int(
                        ((schedule["team1"] == t) | (schedule["team2"] == t)).sum()
                    ),
                }
            )
    teams = pd.DataFrame(trows)
    teams["wc_win_pct"] = teams.apply(
        lambda r: round(100 * r["wc_wins"] / r["wc_matches"], 1) if r["wc_matches"] else None,
        axis=1,
    )
    phases = pd.DataFrame(PHASES, columns=["phase", "description", "start", "end", "matches"])
    phases["start"] = pd.to_datetime(phases["start"]).dt.date
    phases["end"] = pd.to_datetime(phases["end"]).dt.date
    qual = pd.DataFrame(QUALIFICATION, columns=["stage", "detail", "date", "status", "teams"])
    qual["date"] = pd.to_datetime(qual["date"]).dt.date
    src = pd.DataFrame(SOURCES, columns=["source", "url", "kind", "used_for"])
    src["checked"] = CHECKED
    tables = {
        "schedule": schedule,
        "venues": venues,
        "teams": teams,
        "phases": phases,
        "qualification": qual,
        "sources": src,
    }
    for name, df in tables.items():
        d = OUT / "data" / "gold" / name
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "part-0.parquet", index=False)
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    try:
        con.execute("create schema if not exists gold")
        for name in tables:
            src_path = (OUT / "data" / "gold" / name / "part-0.parquet").as_posix()
            con.execute(
                f"create or replace table gold.{name} as select * from read_parquet('{src_path}')"
            )
    finally:
        con.close()
    summary = {
        "checked": CHECKED,
        "matches": len(schedule),
        "venues": len(venues),
        "teams_confirmed": int(teams["confirmed"].sum()),
        "team_slots": len(teams),
        "sources_agree": int(schedule["sources_agree"].fillna(False).sum()),
        "sources_disagree": int((schedule["sources_agree"] == False).sum()),  # noqa: E712
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(build_all())
