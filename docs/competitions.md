# Champions Trophy and World Test Championship

Added after the World Cups. They live beside the World Cup data and never change its numbers.

| | World Cups | Champions Trophy | Test Championship |
|---|---|---|---|
| Editions | 16 | 7 (2002, 2004, 2006, 2009, 2013, 2017, 2025) | 4 cycles (2019-21, 2021-23, 2023-25, 2025-27 in progress) |
| Matches | 677 | 112 (all scheduled, incl. 3 abandoned / rained off in 2025) | 245 (61 + 70 + 70 + 44 so far) |
| Sources | ESPNcricinfo + Cricsheet | Cricsheet ball-by-ball + ESPNcricinfo (schedule, scorecards, squads, points tables) | same; cycle membership from ESPNcricinfo's series schedule |
| Ball-by-ball | 75% of matches | every match except 2002 and the abandoned ones | every played match |
| Gold layer | `data/gold` | `data/competitions/ct/data/gold` | `data/competitions/wtc/data/gold` |
| DuckDB | `cricket_gold.duckdb` | `cricket_gold_ct.duckdb` | `cricket_gold_wtc.duckdb` |

Run: `python scripts/run_competitions.py` (also the last step of the lakehouse pipeline).

1. `src/competitions/fetch.py` downloads the two open Cricsheet archives once (`data/raw/competitions`, sha256 manifest).
2. `src/competitions/espn.py` uses the project's own collector (identifying user agent, robots.txt, throttling, hard stop
   on 401/403/429) to fetch, per edition: the schedule (every match, including abandoned ones), the points table, squads
   and the scorecards. Raw HTML goes to `data/raw/competitions/espn/`, parsed JSON to `data/competitions/espn/`.
   Re-runs use the cached pages.
3. `src/competitions/silver_cricsheet.py` + `espn_silver.py` build the silver tables in the schema the existing gold builder
   reads. Cricsheet names are resolved against the match's own ESPNcricinfo roster (the same method as the World Cups), so a
   player has one id across competitions. Matches that only ESPNcricinfo has become scorecard-only matches.
4. `build_gold` (unchanged apart from Test support), then DuckDB, then `reports/competitions_report.md`.

## Checks

Every innings total and wicket count built from the ball-by-ball (1,144 innings) equals the independent ESPNcricinfo
scorecard (`tests/test_competitions.py`). Winners and runners-up are derived from the final's result, not typed in.

## What is and is not covered

- **No 2026 Champions Trophy exists** (the next is 2029).
- **2002**: no ball-by-ball exists anywhere open, so it is scorecard-only. The final was washed out on both days
  (reserve day too): India and Sri Lanka are joint champions (`joint_winners` in `config/competitions.yaml`), runner-up empty.
- **Squads**: official squads (captain, roles, birth date, styles) from ESPNcricinfo for 2009, 2013, 2017 and 2025. For
  2002, 2004 and 2006 ESPNcricinfo has no squad list, so the squad is the players named in a playing XI (`source` says
  `playing_xi`; no captain or roles).
- **Player of the tournament** comes from `config/competition_awards.csv` (supplied by the project owner). The World Test
  Championship has no overall award: the value shown is the final's player of the match (the page says "Player of the final").
- **Test Championship**: each edition is a cycle with every Test that counted. 5 matches of 2019-21 were postponed and never
  played, so 61 were played. The 2025-27 cycle is still in progress (no final yet, no champion). The points table is
  ESPNcricinfo's (points, played, won, lost); the `ties` column holds draws for Tests.
- **Logos**: your logos for 2002-2025 and the three finals are in `web/public/logos`. The in-progress 2025-27 cycle uses
  the ICC logo (drop `wtc-2027.png` there to replace it).
- Machine Learning and the World Cup statistics page are trained on World Cup data only and are not offered for these
  competitions; they have their own **Statistics** page (toss, batting first, scoring trends, team strength with confidence
  intervals, phases) computed from their data.

## Test cricket in gold

Phases for Tests: overs 1-15 are stored as "powerplay" (new ball), 16-80 "middle", 81+ "death" (old ball). The last
innings of a Test is the chase. A batter with two innings has two rows in `fact_player_performances`; bowling and
fielding totals sit on the first row so they are not counted twice. Penalty runs are added to the innings total (they are
listed outside the ball-by-ball in the source).

## ICC Men's Cricket World Cup 2027 (upcoming)

South Africa, Zimbabwe and Namibia, 2 October to 21 November 2027. It has not been played, so the project holds only
published information (no results, no invented team lists): `python scripts/run_competitions.py --wc2027`.

| Table (`data/competitions/wc27`, DuckDB `cricket_gold_wc27.duckdb`) | Content |
|---|---|
| `schedule` | all 57 fixtures: date, phase, group, teams or published seeds (A1, B2...), ground, city, country, reserve days |
| `venues` | 12 grounds: capacity (Wikipedia), approximate location, matches, past World Cup record at the same ground (project data) |
| `teams` | 12 slots (10 confirmed teams + Qualifier A and B), group, how they qualified, Super 7 seed, ODI World Cup record 2003-2023 |
| `phases`, `qualification`, `sources` | format, qualification path with status, sources and the date they were checked (2026-11-04) |

- **Schedule**: `config/wc2027_icc_fixtures.csv` is the official ICC fixture list; ESPNcricinfo's schedule (fetched with the
  project's collector) is compared fixture by fixture. All 57 agree (ESPNcricinfo leaves the unknown qualifier blank).
- **Teams**: South Africa and Zimbabwe (hosts) and India, Australia, Pakistan, Afghanistan, New Zealand, Sri Lanka, England,
  Bangladesh (top eight of the ODI rankings at the 30 September 2026 cut-off) are confirmed. Four places are decided by the
  qualifier (late Feb to late March 2027; sources differ on the exact dates). Ireland, West Indies, Netherlands, Scotland and
  the United States are confirmed for it; the rest is still open. **This changes as qualification finishes:** rebuild then.
- Not published: match start times, ticket information.
