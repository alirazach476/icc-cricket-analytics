# Data Quality Audit

_Generated 2026-11-03 16:09 UTC by `src/profiling/generate_data_audit.py` from the live database and files. Every number below is computed, not typed. Re-run to refresh._

## 1. Scope and method

- **Read-only.** No raw, processed, database or warehouse data was changed; only files under `reports/` are written.
- **Sources audited:** the PostgreSQL tables (full column profiling), the processed JSON files, the manifests, the Parquet exports and the DuckDB warehouse (counted), plus counts of the raw HTML/JSON collections.
- **Checks:** per-column nulls/uniqueness/ranges, duplicate keys and rows, every declared foreign key, 18 cricket-logic relationships (including scorecard and ball-by-ball reconciliation), player/team identity, and Postgres-vs-DuckDB consistency.
- **Not yet done:** the formal quality score (Stage 3). No composite score is given here on purpose.

## 2. Dataset overview

- Tournaments: **16** | matches: **677** | innings: **1326** | deliveries: **193,779**
- Players: **2,521** ({'espn': 1406, 'cricsheet': 1115}) | teams: **28** | distinct venue strings: **83**
- Total runs in innings: **238,089** | total wickets: **8,958** (super overs excluded)

### Format and year distribution

| format | tournaments | matches | first_match | last_match |
|---|---|---|---|---|
| ODI | 6 | 299 | 2003-02-09 | 2023-11-19 |
| T20 | 10 | 378 | 2007-09-11 | 2026-03-08 |

### Coverage by tournament

| tournament_id | matches | completed_matches | no_result_or_abandoned | matches_with_batting_scorecard | completed_with_deliveries | deliveries | scorecard_coverage_pct | ball_by_ball_coverage_pct | ball_by_ball_pct_of_completed |
|---|---|---|---|---|---|---|---|---|---|
| ODI_M_2003 | 54 | 52 | 2 | 52 | 47 | 25390 | 96.3 | 90.7 | 90.4 |
| ODI_M_2007 | 51 | 51 | 0 | 51 | 50 | 26163 | 100.0 | 98.0 | 98.0 |
| ODI_M_2011 | 49 | 48 | 1 | 49 | 48 | 26036 | 100.0 | 100.0 | 100.0 |
| ODI_M_2015 | 49 | 48 | 1 | 48 | 42 | 22541 | 98.0 | 85.7 | 87.5 |
| ODI_M_2019 | 48 | 44 | 4 | 45 | 35 | 19933 | 93.8 | 75.0 | 79.5 |
| ODI_M_2023 | 48 | 48 | 0 | 48 | 39 | 21195 | 100.0 | 81.2 | 81.2 |
| T20_M_2007 | 27 | 26 | 1 | 26 | 0 | 0 | 96.3 | 0.0 | 0.0 |
| T20_M_2009 | 27 | 27 | 0 | 27 | 0 | 0 | 100.0 | 0.0 | 0.0 |
| T20_M_2010 | 27 | 26 | 1 | 27 | 0 | 0 | 100.0 | 0.0 | 0.0 |
| T20_M_2012 | 27 | 26 | 1 | 27 | 0 | 0 | 100.0 | 0.0 | 0.0 |
| T20_M_2014 | 35 | 35 | 0 | 35 | 32 | 7304 | 100.0 | 91.4 | 91.4 |
| T20_M_2016 | 35 | 33 | 2 | 34 | 25 | 5791 | 97.1 | 74.3 | 75.8 |
| T20_M_2021 | 45 | 45 | 0 | 45 | 40 | 9023 | 100.0 | 88.9 | 88.9 |
| T20_M_2022 | 45 | 41 | 4 | 42 | 38 | 9126 | 93.3 | 86.7 | 92.7 |
| T20_M_2024 | 55 | 51 | 4 | 52 | 43 | 9722 | 94.5 | 80.0 | 84.3 |
| T20_M_2026 | 55 | 53 | 2 | 53 | 49 | 11555 | 96.4 | 89.1 | 92.5 |

### Match stages

| format | match_stage | matches |
|---|---|---|
| ODI | Group Stage | 240 |
| ODI | Super Eight | 24 |
| ODI | Other | 17 |
| ODI | Semifinal | 12 |
| ODI | Final | 6 |
| T20 | Group Stage | 324 |
| T20 | Super Eight | 24 |
| T20 | Semifinal | 20 |
| T20 | Final | 10 |

## 3. Findings (ranked)

### High (4)

- **[Identity]** Players exist under two ID schemes (ESPN and Cricsheet-derived); ball-by-ball and scorecards cannot be joined per player until resolved.  
  _Evidence:_ 261 names map to both an espn_ and a cricsheet_ id; 1052 distinct delivery batters carry cricsheet ids; none of the 1240 scorecard batters share an id with a delivery batter. Initial-vs-full-name variants (e.g. 'JM Bairstow' vs 'Jonny Bairstow') are not counted here and will add more.
- **[Coverage]** 166 completed matches have no ball-by-ball data.  
  _Evidence:_ ODI_M_2003: 47/52; ODI_M_2007: 50/51; ODI_M_2015: 42/48; ODI_M_2019: 35/44; ODI_M_2023: 39/48; T20_M_2007: 0/26; T20_M_2009: 0/27; T20_M_2010: 0/26; T20_M_2012: 0/26; T20_M_2014: 32/35; T20_M_2016: 25/33; T20_M_2021: 40/45; T20_M_2022: 38/41; T20_M_2024: 43/51; T20_M_2026: 49/53. No ball-by-ball at all for: T20_M_2007, T20_M_2009, T20_M_2010, T20_M_2012.
- **[Integrity]** Relationship violated: match winner is one of the two teams  
  _Evidence:_ 4 of 644 rows.  Examples: (1415709, T20_M_2024, espn_20, espn_35, espn_34, Uganda won by 3 wickets (with 10 balls remaining)); (1512751, T20_M_2026, espn_30, espn_33, espn_32, Nepal won by 7 wickets (with 4 balls remaining)); (682899, T20_M_2014, espn_33, espn_19, espn_32, Nepal won by 80 runs); (682913, T20_M_2014, espn_33, espn_40, espn_32, Nepal won by 9 runs)
- **[Integrity]** Relationship violated: toss winner is one of the two teams  
  _Evidence:_ 5 of 664 rows.  Examples: (1415705, T20_M_2024, espn_40, espn_35, espn_34); (1415709, T20_M_2024, espn_20, espn_35, espn_34); (1415731, T20_M_2024, espn_3, espn_33, espn_32); (1415737, T20_M_2024, espn_25, espn_33, espn_32); (1512751, T20_M_2026, espn_30, espn_33, espn_32)

### Medium (11)

- **[Integrity]** Relationship needs review: tie-break winner is recorded in winner_id  
  _Evidence:_ 6 of 10 rows. tied matches decided by super over / boundary count / eliminator name a winner only in result_margin text Examples: (1144530, ODI_M_2019, Match tied (England won on boundary count)); (1415703, T20_M_2024, Match tied (Namibia won the Super Over)); (1415711, T20_M_2024, Match tied (U.S.A. won the Super Over)); (1512731, T20_M_2026, Match tied (South Africa won the 2nd Super Over)); (533284, T20_M_2012, Match tied (Sri Lanka won the one-over eliminator)); (533292, T20_M_2012, Match tied (West Indies won the one-over eliminator))
- **[Integrity]** Relationship needs review: row count collection_runs  
  _Evidence:_ 2 of 48 rows. warehouse out of date
- **[Completeness]** collection_runs: columns that are entirely null.  
  _Evidence:_ source_id, match_id
- **[Completeness]** Table data_quality_results is empty.  
  _Evidence:_ 0 rows
- **[Completeness]** deliveries: columns that are entirely null.  
  _Evidence:_ commentary_text
- **[Completeness]** Table match_events is empty.  
  _Evidence:_ 0 rows
- **[Completeness]** matches: columns that are entirely null.  
  _Evidence:_ match_type, umpires, match_referee
- **[Completeness]** teams: columns that are entirely null.  
  _Evidence:_ country_code
- **[Completeness]** Table tournament_awards is empty.  
  _Evidence:_ 0 rows
- **[Completeness]** tournaments: columns that are entirely null.  
  _Evidence:_ number_of_matches
- **[Consistency]** Teams without a real name (name equals id); they appear to be alias ids.  
  _Evidence:_ ['espn_32', 'espn_34']; never used as team1/team2, but referenced as winner or toss winner in 7 matches. Compare with the winner/toss examples above.

### Low (9)

- **[Completeness]** batting_scorecards: columns with substantial missing values.  
  _Evidence:_ runs 23%, balls_faced 23%, fours 23%, sixes 23%, strike_rate 23%, dismissal 23%, dismissal_type 23%, dismissed_by 38%, fielder 55%
- **[Completeness]** collection_runs: columns with substantial missing values.  
  _Evidence:_ tournament_id 25%, finished_at 73%, error_message 81%
- **[Completeness]** deliveries: columns with substantial missing values.  
  _Evidence:_ extras_type 96%, dismissal_type 96%, dismissed_player_id 96%, fielder_id 98%
- **[Completeness]** innings: columns with substantial missing values.  
  _Evidence:_ target 50%
- **[Completeness]** players: columns with substantial missing values.  
  _Evidence:_ batting_style 94%, bowling_style 94%, date_of_birth 94%, source_url 51%, collected_at 51%
- **[Completeness]** squads: columns with substantial missing values.  
  _Evidence:_ note 99%
- **[Consistency]** Team short names are inconsistent (some are full words).  
  _Evidence:_ KENYA, SCOT
- **[Consistency]** Match stage 'Other' is ambiguous (pre-knockout rounds such as Super Six or quarterfinals).  
  _Evidence:_ 17 matches; needs a proper stage taxonomy before stage-based analysis
- **[Modelling]** Venues are free text with no venue dimension, so venue analysis depends on string cleaning.  
  _Evidence:_ 83 distinct venue strings, 75 cities

## 4. Relationship checks

| relationship | checked_rows | violating_rows | status | detail | examples |
|---|---|---|---|---|---|
| every match has innings | 677 | 16 | info | abandoned, no-result and walkover matches legitimately have none; real errors are caught by the RESULT check |  |
| walkover matches (no ball bowled) | 654 | 2 | info | legitimate: result awarded without play; excluded from batting/ball-by-ball analyses |  |
| every match has batting scorecards | 677 | 16 | info |  |  |
| match winner is one of the two teams | 644 | 4 | fail |  | (1415709, T20_M_2024, espn_20, espn_35, espn_34, Uganda won by 3 wickets (with 10 balls remaining)); (1512751, T20_M_2026, espn_30, espn_33, espn_32, Nepal won by 7 wickets (with 4 balls remaining)); (682899, T20_M_2014, espn_33, espn_19, espn_32, Nepal won by 80 runs); (682913, T20_M_2014, espn_33, espn_40, espn_32, Nepal won by 9 runs) |
| toss winner is one of the two teams | 664 | 5 | fail |  | (1415705, T20_M_2024, espn_40, espn_35, espn_34); (1415709, T20_M_2024, espn_20, espn_35, espn_34); (1415731, T20_M_2024, espn_3, espn_33, espn_32); (1415737, T20_M_2024, espn_25, espn_33, espn_32); (1512751, T20_M_2026, espn_30, espn_33, espn_32) |
| tie-break winner is recorded in winner_id | 10 | 6 | warn | tied matches decided by super over / boundary count / eliminator name a winner only in result_margin text | (1144530, ODI_M_2019, Match tied (England won on boundary count)); (1415703, T20_M_2024, Match tied (Namibia won the Super Over)); (1415711, T20_M_2024, Match tied (U.S.A. won the Super Over)); (1512731, T20_M_2026, Match tied (South Africa won the 2nd Super Over)); (533284, T20_M_2012, Match tied (Sri Lanka won the one-over eliminator)); (533292, T20_M_2012, Match tied (West Indies won the one-over eliminator)) |
| RESULT matches without a winner (ties) | 654 | 10 | info | genuine ties; target definition for win/loss models must handle them explicitly |  |
| row count collection_runs | 48 | 2 | warn | warehouse out of date |  |

83 of 91 checks passed. Rows marked `info` are legitimate cricket events reported for transparency, not defects.

## 5. Limitations of this audit

- Name-based identity matching only catches exact name matches; initial/full-name variants need Stage 4 resolution.
- A 'RESULT' match with no winner may be a legitimate tie or super-over decision; it is flagged for review, not asserted as an error.
- Reconciliation can only be checked where both sides exist (ball-by-ball totals exist for matches with deliveries only).
- Raw HTML/JSON collections are counted, not parsed; their content is audited through the processed layer.

## 6. Reproduce

```powershell
python scripts/run_profiling.py
```
