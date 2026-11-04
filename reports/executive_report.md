# Men's ICC World Cups - analytics report

_Generated 2026-11-03 19:44 UTC from the gold layer. Every figure below is computed from the data or from the stage reports._

## 1. Summary

* **Scope:** 16 men's World Cups (ODI 2003-2023 (6 editions); T20 2007-2026 (10 editions)), 677 matches, 1,418 players, 26 teams, 79 venues, 193,779 balls bowled.
* **Coverage:** every match has a scorecard; ball-by-ball exists for 488 of 652 played matches (75%). The rest are not in the free ball-by-ball source.
* **Quality:** 22 data-quality rules on the resolved data; overall dataset scores 97.9-100.0/100.
* **Cricket findings:** 9 of 20 hypothesis tests stay significant after multiple-testing correction (section 4).
* **Prediction:** an Elo rating alone predicts match winners 66% of the time out of sample (coin: 49%). Best richer model by log-loss: random_forest (0.595 vs Elo-only 0.597), i.e. not clearly better than Elo.

## 2. The data

Champions by edition:

| format | year | winner | runner_up | player_of_tournament |
|---|---|---|---|---|
| ODI | 2003 | Australia | India | Sachin Tendulkar |
| ODI | 2007 | Australia | Sri Lanka | Glenn McGrath |
| ODI | 2011 | India | Sri Lanka | Yuvraj Singh |
| ODI | 2015 | Australia | New Zealand | Mitchell Starc |
| ODI | 2019 | England | New Zealand | Kane Williamson |
| ODI | 2023 | Australia | India | Virat Kohli |
| T20 | 2007 | India | Pakistan | Shahid Afridi |
| T20 | 2009 | Pakistan | Sri Lanka | Tillakaratne Dilshan |
| T20 | 2010 | England | Australia | Kevin Pietersen |
| T20 | 2012 | West Indies | Sri Lanka | Shane Watson |
| T20 | 2014 | Sri Lanka | India | Virat Kohli |
| T20 | 2016 | West Indies | England | Virat Kohli |
| T20 | 2021 | Australia | New Zealand | David Warner |
| T20 | 2022 | England | Pakistan | Sam Curran |
| T20 | 2024 | India | South Africa | Jasprit Bumrah |
| T20 | 2026 | India | New Zealand | Sanju Samson |

Titles by team:

| team_name | format | titles |
|---|---|---|
| Australia | ODI | 4 |
| India | T20 | 3 |
| England | T20 | 2 |
| West Indies | T20 | 2 |
| England | ODI | 1 |
| India | ODI | 1 |
| Australia | T20 | 1 |
| Pakistan | T20 | 1 |
| Sri Lanka | T20 | 1 |

Why some matches lack ball-by-ball detail:

| status | matches |
|---|---|
| has ball-by-ball | 495 |
| not_in_cricsheet_world_cup_bundle | 164 |
| no_result_or_abandoned | 16 |
| walkover_no_play | 2 |

ODI data begins with the 2003 World Cup, so career totals cover 2003-2023 only (earlier ODI World Cups are not in the dataset).

## 3. Data quality

| dataset | completeness | uniqueness | validity | referential_integrity | consistency | historical_coverage | overall |
|---|---|---|---|---|---|---|---|
| gold.dim_players | - | 99.7 | - | - | - | - | 99.7 |
| gold.dim_venues | - | 100.0 | - | - | - | - | 100.0 |
| gold.fact_deliveries | - | - | 100.0 | 100.0 | - | - | 100.0 |
| gold.fact_innings | - | - | - | - | 100.0 | - | 100.0 |
| gold.fact_matches | 100.0 | - | - | 100.0 | 100.0 | 91.6 | 97.9 |
| gold.fact_player_performances | - | - | 100.0 | - | - | - | 100.0 |
| gold.fact_tournament_standings | - | - | - | - | 100.0 | - | 100.0 |
| gold.mart_data_coverage | - | - | - | - | - | 100.0 | 100.0 |

Rules with failures (each is explained in `reports/gold/data_quality_report.md`; `-` above means the dimension has no rule for that dataset):

| rule_id | severity | total | failed |
|---|---|---|---|
| gold.ball_by_ball_available | minor | 652 | 164 |
| gold.deliveries_player_resolved | minor | 193779 | 23 |
| gold.innings_wickets_match_deliveries | critical | 991 | 1 |
| gold.player_unique_name_dob | minor | 1418 | 4 |

## 4. Findings

Records from the data:

* Highest individual score: **Martin Guptill** 237 (2015, v West Indies).
* Best bowling: **Glenn McGrath** 7/15 (2003).
* Highest team total: **South Africa** 428 (2023).
* Lowest all-out total: **Canada** 36 (2003).
* Biggest win by runs: **Australia** over Netherlands by 309 (2023).

Hypothesis tests (Holm-corrected p-values; matches are not independent draws, so p-values are indicative):

| test_id | n | effect_name | effect | p_holm | significant_at_0.05 |
|---|---|---|---|---|---|
| toss_win_rate_ODI | 285 | toss winner win rate | 0.481 | 1.000 | False |
| toss_win_rate_T20 | 357 | toss winner win rate | 0.515 | 1.000 | False |
| bat_first_win_rate_ODI | 285 | bat-first win rate | 0.540 | 1.000 | False |
| bat_first_win_rate_T20 | 357 | bat-first win rate | 0.507 | 1.000 | False |
| bat_first_trend_ODI | 285 | odds ratio per year | 0.993 | 1.000 | False |
| bat_first_trend_T20 | 357 | odds ratio per year | 0.994 | 1.000 | False |
| toss_decision_ODI | 285 | Cramer's V | 0.082 | 1.000 | False |
| toss_decision_T20 | 357 | Cramer's V | 0.022 | 1.000 | False |
| scoring_trend_ODI | 265 | runs per year | 3.032 | <0.001 | True |
| scoring_trend_T20 | 340 | runs per year | 0.251 | 1.000 | False |
| chase_vs_target_ODI | 265 | odds ratio per +10 runs of target | 0.755 | <0.001 | True |
| chase_vs_target_T20 | 340 | odds ratio per +10 runs of target | 0.685 | <0.001 | True |
| venue_effect_ODI | 85 | epsilon-squared | 0.231 | 0.599 | False |
| venue_effect_T20 | 287 | epsilon-squared | 0.255 | <0.001 | True |
| host_advantage_ODI | 78 | host win rate | 0.705 | 0.005 | True |
| host_advantage_T20 | 63 | host win rate | 0.603 | 1.000 | False |
| dot_ball_phase_ODI | 141245 | Cramer's V | 0.160 | <0.001 | True |
| dot_ball_phase_T20 | 52492 | Cramer's V | 0.153 | <0.001 | True |
| sixes_trend_ODI | 289 | rate ratio per year | 1.044 | <0.001 | True |
| sixes_trend_T20 | 363 | rate ratio per year | 1.020 | <0.001 | True |

No detectable edge from winning the toss or batting first (toss_win_rate_ODI, toss_win_rate_T20, bat_first_win_rate_ODI, bat_first_win_rate_T20: all within chance).

## 5. Predictive modelling

Who wins (expanding-window evaluation: trained on earlier tournaments, tested on the next):

| model | n | accuracy | log_loss | brier | auc | precision | recall | f1 |
|---|---|---|---|---|---|---|---|---|
| coin | 465 | 0.488 | 0.693 | 0.250 | 0.500 | 0.000 | 0.000 | 0.000 |
| elo_only | 465 | 0.660 | 0.597 | 0.205 | 0.751 | 0.672 | 0.655 | 0.664 |
| logistic | 465 | 0.686 | 0.604 | 0.207 | 0.744 | 0.681 | 0.727 | 0.703 |
| random_forest | 465 | 0.682 | 0.595 | 0.204 | 0.748 | 0.667 | 0.756 | 0.709 |
| grad_boosting | 465 | 0.662 | 0.618 | 0.211 | 0.733 | 0.655 | 0.718 | 0.685 |
| xgboost | 465 | 0.673 | 0.602 | 0.206 | 0.746 | 0.659 | 0.748 | 0.701 |
| logistic_squad | 465 | 0.682 | 0.600 | 0.205 | 0.751 | 0.677 | 0.723 | 0.699 |
| logistic_by_format | 465 | 0.673 | 0.617 | 0.210 | 0.738 | 0.676 | 0.693 | 0.685 |
| random_forest_by_format | 465 | 0.699 | 0.599 | 0.205 | 0.744 | 0.678 | 0.786 | 0.728 |

Do extra features help? (same protocol, logistic model):

| feature_set | n_features | n_test | log_loss | accuracy |
|---|---|---|---|---|
| elo_diff only | 1 | 465 | 0.590 | 0.667 |
| elo + runs for/against | 3 | 465 | 0.588 | 0.675 |
| team strength family | 6 | 465 | 0.599 | 0.652 |
| no toss, no venue | 10 | 465 | 0.604 | 0.682 |
| all features | 13 | 465 | 0.604 | 0.686 |

Reading: the Elo gap alone is at least as good as all features, so the extra features add noise at this sample size.

Live first-innings projection (during the innings), linear regression on remaining runs: ODI: 12.2 runs better than run-rate extrapolation (95% interval 8.0 to 16.2); T20: 3.5 runs better than run-rate extrapolation (95% interval 1.8 to 5.0). Full per-over results are in the machine learning report.

First-innings score (MAE in runs, lower is better):

| model | n | mae | rmse | r2 |
|---|---|---|---|---|
| baseline_format_mean | 456 | 44.24 | 58.26 | 0.48 |
| baseline_venue_mean | 456 | 43.18 | 58.18 | 0.48 |
| ridge | 456 | 40.47 | 53.19 | 0.57 |
| grad_boosting | 456 | 44.78 | 59.87 | 0.45 |

## 6. Limitations

* Ball-by-ball detail covers 75% of played matches; phase and dot-ball analyses use only those.
* Pitch, weather and day/night data were not collected. A synthetic placeholder table exists for demos and is excluded from every analysis in this report.
* About 640 decided matches: small samples limit model complexity; small effects are noise.
* Several matches have no winner (ties without a tie-break, no results, abandoned); they are kept and labelled, never invented.
* Player identity across the two sources is resolved per match with strict rules; a small share of deliveries (<0.1%) could not be matched safely and keep a source-only identity.

## 7. Reproducibility

* Environment: Python 3.12.10, DuckDB 2.0.0.
* Run everything: `python scripts/run_lakehouse_pipeline.py` (details in README); the raw collected data is never modified, and bronze is verified against a content-hash manifest.
* Last pipeline run `20261103T185434Z`: succeeded (18 steps).
