# Data Quality Report

_Generated 2026-11-03 16:29 UTC by `scripts/run_data_quality.py` from the live PostgreSQL data. All figures are computed; re-run to refresh._

## 1. Research objective

Measure how trustworthy each part of the collected World Cup data is, for every tournament and dataset, using explicit, reproducible rules. The goal is to locate defects precisely, not to produce a single grade.

## 2. Dataset used

The PostgreSQL analytical database (tournaments, matches, innings, deliveries, scorecards, players, teams, standings, squads). **130 rules** ran over 3,156,646 row checks.

## 3. Methodology

Every rule counts `failed` rows out of `total` rows checked, per tournament. `pass rate = 1 - failed / total`.

| Dimension | What it measures |
|---|---|
| completeness | required values are present |
| uniqueness | no duplicate entities or keys |
| validity | values are in legal ranges / sets |
| referential_integrity | references point at the right rows (declared FKs and cricket logic) |
| consistency | related values agree (scorecard vs ball-by-ball vs result text) |
| historical_coverage | data that should exist for a played match / tournament does exist |

- **Dimension score** = severity-weighted mean pass rate of its rules (critical x3, major x2, minor x1).
- **Overall** = plain mean of the available dimension scores (equal weights). It is only a summary.
- Rules pooled **per rule** before dataset scores, so large tournaments do not dominate by row count.
- `(global)` rows are checks without a tournament (e.g. declared foreign keys).

## 4. Data limitations

- Scores are only comparable within this rule set; adding rules changes them.
- Coverage rules compare against what *should* exist, not what any source can provide. Ball-by-ball for T20 2007-2012 is unavailable from every free source checked, so that is a coverage gap, not a defect.
- Some rules can raise false positives (see the 'note' column in the failing-rule table).
- Rules cannot detect errors that are internally consistent (e.g. a wrong but self-consistent score).

## 5. Results

### Scores by tournament (0-100)

| tournament_id | completeness | uniqueness | validity | ref_integrity | consistency | coverage | overall | critical_rules_failing |
|---|---|---|---|---|---|---|---|---|
| T20_M_2012 | 82.8 | 94.7 | 100.0 | 100.0 | 99.8 | 81.8 | 93.2 | 1 |
| T20_M_2009 | 85.7 | 94.5 | 100.0 | 100.0 | 99.8 | 81.8 | 93.6 | 1 |
| T20_M_2010 | 85.7 | 94.6 | 100.0 | 100.0 | 99.5 | 81.8 | 93.6 | 1 |
| T20_M_2007 | 85.7 | 94.7 | 100.0 | 100.0 | 99.7 | 81.8 | 93.7 | 1 |
| ODI_M_2019 | 84.2 | 94.7 | 99.6 | 100.0 | 95.1 | 96.3 | 95.0 | 3 |
| T20_M_2024 | 83.3 | 94.1 | 99.4 | 97.3 | 99.6 | 97.1 | 95.2 | 5 |
| T20_M_2014 | 86.5 | 92.6 | 100.0 | 98.4 | 99.6 | 98.4 | 95.9 | 2 |
| T20_M_2026 | 83.7 | 94.1 | 100.0 | 99.0 | 99.7 | 98.6 | 95.9 | 3 |
| T20_M_2016 | 87.1 | 93.9 | 100.0 | 100.0 | 99.9 | 95.6 | 96.1 | 1 |
| ODI_M_2023 | 87.1 | 93.9 | 100.0 | 100.0 | 99.8 | 96.6 | 96.2 | 1 |
| ODI_M_2003 | 83.9 | 96.3 | 99.5 | 100.0 | 99.5 | 98.9 | 96.3 | 1 |
| ODI_M_2015 | 87.1 | 94.1 | 99.8 | 100.0 | 99.7 | 97.7 | 96.4 | 1 |
| T20_M_2021 | 87.1 | 94.9 | 100.0 | 100.0 | 99.9 | 98.0 | 96.6 | 1 |
| T20_M_2022 | 87.1 | 94.9 | 100.0 | 100.0 | 99.6 | 98.7 | 96.7 | 1 |
| ODI_M_2007 | 87.1 | 96.3 | 99.9 | 100.0 | 99.5 | 99.6 | 97.1 | 1 |
| ODI_M_2011 | 87.1 | 95.7 | 99.8 | 100.0 | 99.8 | 100.0 | 97.1 | 1 |

### Scores by dataset (0-100)

| dataset | completeness | uniqueness | validity | ref_integrity | consistency | coverage | overall | rules_evaluated | rules_failing | critical_rules_failing |
|---|---|---|---|---|---|---|---|---|---|---|
| coverage |  |  |  |  |  | 95.4 | 95.4 | 6 | 1 | 0 |
| deliveries | 100.0 | 100.0 | 100.0 |  | 100.0 |  | 100.0 | 10 | 0 | 0 |
| innings | 99.5 | 100.0 | 99.7 | 100.0 | 99.3 |  | 99.7 | 15 | 6 | 2 |
| matches | 90.9 | 100.0 | 99.8 | 99.3 | 99.8 |  | 98.0 | 19 | 5 | 2 |
| players | 71.4 | 79.1 |  |  | 99.8 |  | 83.4 | 6 | 4 | 1 |
| relationships |  |  |  | 100.0 |  |  | 100.0 | 50 | 0 | 0 |
| squads |  |  | 100.0 |  | 100.0 |  | 100.0 | 2 | 0 | 0 |
| standings | 93.4 |  | 100.0 | 100.0 | 100.0 |  | 98.4 | 5 | 1 | 0 |
| teams | 73.7 |  |  |  | 98.3 |  | 86.0 | 4 | 4 | 0 |
| tournaments | 66.7 |  | 100.0 |  | 96.9 |  | 87.8 | 5 | 2 | 0 |

### Failing rules (23 of 130; 107 rules passed on every row)

| severity | rule_id | failed | total_all | fail_pct | tournaments_affected | examples | note |
|---|---|---|---|---|---|---|---|
| critical | players.single_identity | 1155 | 5537 | 20.86 | 16 | cricsheet_abdul_razzaq, cricsheet_adeel_raja, cricsheet_akram_khan, cricsheet_al_sahariar, cricsheet_alok_kapali | exact-name matches only; initial-vs-full-name variants are not detected here |
| critical | matches.toss_winner_is_participant | 5 | 664 | 0.75 | 2 | 1415705, 1415709, 1415731, 1415737, 1512751 |  |
| critical | matches.winner_is_participant | 4 | 644 | 0.62 | 3 | 682899, 682913, 1415709, 1512751 |  |
| critical | innings.runs_non_negative | 6 | 1326 | 0.45 | 2 | 1144530_3, 1144530_4, 1415703_3, 1415703_4, 1415711_3 | failures are super-over innings whose totals were never stored (derivable from deliveries) |
| critical | innings.wickets_in_range | 6 | 1326 | 0.45 | 2 | 1144530_3, 1144530_4, 1415703_3, 1415703_4, 1415711_3 |  |
| major | coverage.played_matches_have_ball_by_ball | 164 | 652 | 25.15 | 15 | 1384394, 1384400, 1384404, 1384407, 1384413 | data is unavailable at every free source for T20 2007-2012, so this is a coverage gap, not a defect |
| major | tournaments.winner_won_the_final | 1 | 16 | 6.25 | 1 | ODI_M_2019 |  |
| major | teams.referenced_team_has_real_name | 4 | 234 | 1.71 | 3 | espn_34, espn_32, espn_32, espn_32 | alias ids such as espn_32 / espn_34 (Nepal / Uganda) fail here |
| major | innings.wickets_match_deliveries | 13 | 991 | 1.31 | 9 | 1273750_2, 1298163_1, 1384402_2, 1384429_1, 1415708_2 | retired-out and similar dismissals may legitimately differ |
| major | innings.overs_present | 10 | 1326 | 0.75 | 3 | 1512731_3, 1512731_4, 1512731_5, 1512731_6, 1144530_3 |  |
| major | innings.legal_balls_within_limit | 4 | 985 | 0.41 | 3 | 1144512_1, 247475_1, 247493_1, 65266_1 |  |
| minor | matches.tiebreak_winner_recorded | 6 | 6 | 100.0 | 4 | 1512731, 533284, 533292, 1144530, 1415703 |  |
| minor | players.birth_date_present | 5537 | 5537 | 100.0 | 16 | cricsheet_a_bagai, cricsheet_a_codrington, cricsheet_a_flintoff, cricsheet_a_flower, cricsheet_a_kumble |  |
| minor | players.styles_present | 5537 | 5537 | 100.0 | 16 | cricsheet_a_bagai, cricsheet_a_codrington, cricsheet_a_flintoff, cricsheet_a_flower, cricsheet_a_kumble |  |
| minor | teams.country_code_present | 234 | 234 | 100.0 | 16 | espn_8, espn_27, espn_1, espn_15, espn_29 |  |
| minor | tournaments.number_of_matches_present | 16 | 16 | 100.0 | 16 | T20_M_2007, ODI_M_2003, ODI_M_2007, ODI_M_2011, ODI_M_2015 |  |
| minor | standings.qualified_flag_present | 20 | 304 | 6.58 | 1 | 1, 2, 3, 4, 5 |  |
| minor | innings.target_matches_first_innings | 39 | 655 | 5.95 | 13 | 1144489_2, 1144503_2, 1144504_2, 1298152_2, 1298154_2 | rain-adjusted (DLS) targets legitimately differ; no DLS flag exists in the data |
| minor | matches.stage_in_taxonomy | 17 | 677 | 2.51 | 3 | 433600, 433601, 433602, 433603, 65275 | 'Other' holds Super Six / quarterfinal matches; fixed by a stage taxonomy in Stage 4 |
| minor | teams.short_name_format | 4 | 230 | 1.74 | 4 | espn_26, espn_26, espn_26, espn_26 |  |
| minor | teams.short_name_present | 4 | 234 | 1.71 | 3 | espn_34, espn_32, espn_32, espn_32 |  |
| minor | matches.winner_named_in_result_text | 9 | 644 | 1.4 | 4 | 1298144, 1415701, 1512738, 1512739, 1512744 | name-format differences ('U.S.A.' vs 'United States of America') cause false positives; alias team ids (name = id) also fail here |
| minor | players.batter_in_tournament_squad | 34 | 14488 | 0.23 | 4 | 1848, 1958, 2143, 2217, 2319 | squad lists can omit late replacements |

## 6. Interpretation

- **5 critical rules** have failures: `players.single_identity`, `matches.toss_winner_is_participant`, `matches.winner_is_participant`, `innings.runs_non_negative`, `innings.wickets_in_range`.
- Highest overall score: **ODI_M_2011 (97.1)**; lowest: **T20_M_2012 (93.2)**. The lowest tournament's weakest dimension is **historical_coverage** (81.8), against 97.4 as the median across tournaments.
- Across tournaments the validity score ranges 99.4-100.0 and consistency 95.1-99.9; coverage ranges 81.8-100.0 and completeness 82.8-87.1.
- Failures marked with a `note` may be legitimate cricket events or source limitations; treat them as review items rather than proven errors.

## 7. Conclusion

Averaged over tournaments, the weakest dimensions are completeness (85.7), historical_coverage (93.9); the strongest are referential_integrity (99.7), validity (99.9). The most material failing rules (critical/major, by failure rate) are `players.single_identity` (20.86%), `matches.toss_winner_is_participant` (0.75%), `matches.winner_is_participant` (0.62%), `innings.runs_non_negative` (0.45%). Dimension scores near 100 mean the rules found few defects, not that the data is proven correct: rules only detect what they test (see limitations).

## 8. Reproduce

```powershell
python scripts/run_data_quality.py            # reports only
python scripts/run_data_quality.py --persist  # also refresh data_quality_results
```

Detail files: `reports/data_quality/` (rule_results, tournament_scores, dataset_scores, rule_catalog). 1142 rows written to `data_quality_results`.
