# Data Quality Report

_Generated 2026-11-03 19:42 UTC by `scripts/run_data_quality.py` from the live PostgreSQL data. All figures are computed; re-run to refresh._

## 1. Research objective

Measure how trustworthy each part of the collected World Cup data is, for every tournament and dataset, using explicit, reproducible rules. The goal is to locate defects precisely, not to produce a single grade.

## 2. Dataset used

The PostgreSQL analytical database (tournaments, matches, innings, deliveries, scorecards, players, teams, standings, squads). **22 rules** ran over 609,626 row checks.

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
| T20_M_2007 | 100.0 |  | 100.0 | 100.0 | 100.0 | 87.5 | 97.5 | 0 |
| T20_M_2009 | 100.0 |  | 100.0 | 100.0 | 100.0 | 87.5 | 97.5 | 0 |
| T20_M_2012 | 100.0 |  | 100.0 | 100.0 | 100.0 | 87.5 | 97.5 | 0 |
| T20_M_2010 | 100.0 |  | 100.0 | 100.0 | 100.0 | 87.5 | 97.5 | 0 |
| T20_M_2016 | 100.0 |  | 100.0 | 100.0 | 100.0 | 97.0 | 99.4 | 0 |
| ODI_M_2019 | 100.0 |  | 100.0 | 100.0 | 100.0 | 97.4 | 99.5 | 0 |
| ODI_M_2023 | 100.0 |  | 100.0 | 100.0 | 99.7 | 97.7 | 99.5 | 1 |
| T20_M_2024 | 100.0 |  | 100.0 | 100.0 | 100.0 | 98.0 | 99.6 | 0 |
| T20_M_2021 | 100.0 |  | 100.0 | 100.0 | 100.0 | 98.6 | 99.7 | 0 |
| ODI_M_2015 | 100.0 |  | 100.0 | 100.0 | 100.0 | 98.4 | 99.7 | 0 |
| ODI_M_2003 | 100.0 |  | 100.0 | 100.0 | 100.0 | 99.2 | 99.8 | 0 |
| T20_M_2014 | 100.0 |  | 100.0 | 100.0 | 100.0 | 98.9 | 99.8 | 0 |
| T20_M_2022 | 100.0 |  | 100.0 | 99.9 | 100.0 | 99.1 | 99.8 | 0 |
| T20_M_2026 | 100.0 |  | 100.0 | 100.0 | 100.0 | 99.1 | 99.8 | 0 |
| ODI_M_2007 | 100.0 |  | 100.0 | 100.0 | 100.0 | 99.8 | 100.0 | 0 |
| ODI_M_2011 | 100.0 |  | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 0 |

### Scores by dataset (0-100)

| dataset | completeness | uniqueness | validity | ref_integrity | consistency | coverage | overall | rules_evaluated | rules_failing | critical_rules_failing |
|---|---|---|---|---|---|---|---|---|---|---|
| gold.dim_players |  | 99.7 |  |  |  |  | 99.7 | 1 | 1 | 0 |
| gold.dim_venues |  | 100.0 |  |  |  |  | 100.0 | 1 | 0 | 0 |
| gold.fact_deliveries |  |  | 100.0 | 100.0 |  |  | 100.0 | 4 | 1 | 0 |
| gold.fact_innings |  |  |  |  | 100.0 |  | 100.0 | 3 | 1 | 1 |
| gold.fact_matches | 100.0 |  |  | 100.0 | 100.0 | 91.6 | 97.9 | 8 | 1 | 0 |
| gold.fact_player_performances |  |  | 100.0 |  |  |  | 100.0 | 1 | 0 | 0 |
| gold.fact_tournament_standings |  |  |  |  | 100.0 |  | 100.0 | 1 | 0 | 0 |
| gold.mart_data_coverage |  |  |  |  |  | 100.0 | 100.0 | 3 | 0 | 0 |

### Failing rules (4 of 22; 18 rules passed on every row)

| severity | rule_id | failed | total_all | fail_pct | tournaments_affected | examples | note |
|---|---|---|---|---|---|---|---|
| critical | gold.innings_wickets_match_deliveries | 1 | 991 | 0.1 | 1 | 1384429_1 | Bangladesh v Sri Lanka 2023-11-06: Mathews was timed out, which the scorecard counts as a wicket but no ball was bowled, so it has no delivery row |
| minor | gold.ball_by_ball_available | 164 | 652 | 25.15 | 15 | 247459, 656411, 656421, 656431, 656449 | source limitation: not in Cricsheet's World Cup bundle (see ball_by_ball_gap_reason) |
| minor | gold.player_unique_name_dob | 4 | 1418 | 0.28 | 1 | espn_1015399, espn_1160970, espn_1168651, espn_56167 | different people can share a name; flagged for review only |
| minor | gold.deliveries_player_resolved | 23 | 193779 | 0.01 | 1 | 1298135_2_66, 1298135_2_67, 1298135_2_68, 1298135_2_69, 1298135_2_72 | share of deliveries whose batter could not be matched safely to a scorecard player |

## 6. Interpretation

- **1 critical rules** have failures: `gold.innings_wickets_match_deliveries`.
- Highest overall score: **ODI_M_2011 (100.0)**; lowest: **T20_M_2007 (97.5)**. The lowest tournament's weakest dimension is **historical_coverage** (87.5), against 98.2 as the median across tournaments.
- Across tournaments the validity score ranges 100.0-100.0 and consistency 99.7-100.0; coverage ranges 87.5-100.0 and completeness 100.0-100.0.
- Failures marked with a `note` may be legitimate cricket events or source limitations; treat them as review items rather than proven errors.

## 7. Conclusion

Averaged over tournaments, the weakest dimensions are historical_coverage (95.8), consistency (100.0); the strongest are completeness (100.0), uniqueness (nan). The most material failing rules (critical/major, by failure rate) are `gold.innings_wickets_match_deliveries` (0.1%). Dimension scores near 100 mean the rules found few defects, not that the data is proven correct: rules only detect what they test (see limitations).

## 8. Reproduce

```powershell
python scripts/run_data_quality.py            # reports only
python scripts/run_data_quality.py --persist  # also refresh data_quality_results
```

Detail files: `reports/data_quality/` (rule_results, tournament_scores, dataset_scores, rule_catalog). 298 rows written to `data_quality_results`.
