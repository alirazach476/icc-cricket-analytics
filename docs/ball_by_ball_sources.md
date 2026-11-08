# Ball-by-ball coverage and sources

## Where World Cup coverage stands

Played World Cup matches with ball-by-ball: **632 of 695 (91%)**, 234,633 deliveries. Before the T20 additions it was 488 of 652 (75%); the 1999 World Cup (42 matches) is scorecard-only because no open source has its deliveries. Every added innings reconciles to its
scorecard (1,189 of 1,189 innings: runs equal the sum of the deliveries).

| Step | Result |
|---|---|
| Cricsheet World Cup bundles (original source) | 488 matches |
| Cricsheet **all-T20I archive** (`t20s_male_json.zip`), matched by date and teams | **+102 matches**: World Twenty20 2007, 2009, 2010, 2012 and one of 2016. The event bundle left them out because Cricsheet files them under "ICC World Twenty20" |
| Cricsheet all-ODI archive (`odis_male_json.zip`) | 0 of the 30 missing World Cup ODIs are in it (mostly matches involving associate nations) |

Still without ball-by-ball (106 played matches: the 42 of 1999 and 64 more): 30 ODI (2003: 5, 2007: 1, 2015: 6, 2019: 9, 2023: 9) and 34 T20 (2010: 2, 2012: 2,
2014: 3, 2016: 7, 2021: 5, 2022: 3, 2024: 8, 2026: 4). Their gap reason is stored per match in `ball_by_ball_gap_reason`
(the label `not_in_cricsheet_world_cup_bundle` now means "not in any Cricsheet archive checked"). Champions Trophy: 17 played
matches lack it (all 14 of 2002, one of 2004, two of 2025); none are in the all-ODI archive. Every played Test has it.

Reproduce the T20 step: download the archive, copy the matching files into `data/raw/commentary/cricsheet/t20/`, run
`collect_commentary` for those match ids (`--source cricsheet`), `normalize_collected.py --force --match <ids>`, then
`run_lakehouse_pipeline.py --only bronze,silver,gold,verify_bronze,warehouse,quality_gold`.

## CREX: investigated, not used

| Check | Finding (checked 2026-11) |
|---|---|
| robots.txt | allows pages but **disallows `/api/*`**, so its data endpoints are off limits to automated clients |
| Terms and Conditions | access is licensed "solely for personal, non-commercial purposes"; **"no Materials may be modified, copied, reproduced, distributed, republished, or transmitted without the prior written permission"** of the operator |
| Official API or data export | none documented |

This project stores the data in a database, publishes it in a public repository and serves it from a public website, which the
terms do not allow without written permission. **No CREX adapter was built and nothing was collected.** The route that remains
is to ask the operator for written permission or a licensed export (support@crex.com is the contact listed in their terms).

## Other permitted options for the remaining gaps

- ESPNcricinfo commentary through the project's polite collector (robots.txt respected). It typically exposes only a recent-ball
  window, so it gives partial coverage that this project labels `partial`, not complete ball-by-ball.
- Licensed data from the ICC or a commercial provider.
- Leaving those matches as scorecard-only, which is what the dashboard does today, with the reason shown.

## Afghanistan matches (Kaggle copy of Cricsheet data)

Cricsheet withholds Afghanistan men's matches by policy (see its README and cricsheet.org/withheld-matches), so no current
Cricsheet archive has them. The Kaggle dataset "ODI ball by ball 2003 to 2025" (CC0, a copy of earlier Cricsheet data, ends
June 2023) holds 15 of them: 6 from the 2015 and 9 from the 2019 World Cup. `scripts/import_kaggle_odi_bbb.py` loads a
match only when date and both teams match a completed ODI of ours with no ball-by-ball and every innings total (batter
runs + extras) equals our scorecard exactly; all 15 passed, none were skipped. Fielder names are not in that file, so
catches are not credited from it. Still missing: the 9 Afghanistan matches of 2023 (the file ends before them), the 12
T20 matches of 2024/2026 and the other gaps listed above.

### User-supplied CSVs (27 more Afghanistan matches)

`scripts/import_download_bbb.py` loads ball-by-ball CSVs the project owner downloaded (CWC 2023 file; T20 World Cup 2016, 2021,
2022, 2024 files) for matches Cricsheet withholds: 9 of CWC 2023, 7 of 2016, 5 of 2021, 3 of 2022, 3 of 2024. A match loads only
when every innings total equals our scorecard and every player name maps to exactly one player of that team's recorded XI
(spelling variants and initials are matched inside that XI; a name that could map to two players skips the match). Skipped:
2024 Afghanistan v Uganda ("Cosy"), v New Zealand ("Mitchell" - two NZ players), the Papua New Guinea and India matches (the file is one
run short in the chase) and the semi-final (the file's totals do not match the real match). No file covered T20 2026
(4 matches), the 2 Champions Trophy 2025 matches (that competition is built separately) or 1999.
