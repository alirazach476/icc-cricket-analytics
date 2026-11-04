# Machine-learning results (Stage 12)

## Protocol

* Expanding window over tournaments: 11 test tournaments, each scored by a model fit only on tournaments that started earlier (first 5 tournaments are training-only).
* Features come from `src/features/match_features.py` (computed only from earlier matches; leakage tests in `tests/test_features.py`).
* Hyperparameters fixed in advance; nothing tuned on test folds. Baselines: a coin, an Elo-only predictor, running format mean / venue mean for scores.

## Who wins? (team A vs team B, decided matches only)

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

Accuracy difference against the Elo-only baseline (paired bootstrap, 95% interval):

| model | accuracy_minus_elo | ci_low | ci_high | beats_elo_significantly |
|---|---|---|---|---|
| coin | -0.172 | -0.234 | -0.110 | False |
| logistic | 0.026 | -0.009 | 0.062 | False |
| random_forest | 0.022 | -0.009 | 0.054 | False |
| grad_boosting | 0.002 | -0.037 | 0.043 | False |
| xgboost | 0.013 | -0.024 | 0.052 | False |
| logistic_squad | 0.022 | -0.022 | 0.067 | False |
| logistic_by_format | 0.013 | -0.026 | 0.052 | False |
| random_forest_by_format | 0.039 | 0.006 | 0.071 | True |

Calibration of the lowest-log-loss model (`random_forest`): do predicted probabilities match what happened?

| n | mean_predicted | actual_rate |
|---|---|---|
| 93 | 0.211 | 0.215 |
| 93 | 0.395 | 0.366 |
| 93 | 0.544 | 0.548 |
| 93 | 0.638 | 0.602 |
| 93 | 0.784 | 0.828 |

By format:

| scope | model | n | accuracy | log_loss | brier | auc | precision | recall | f1 |
|---|---|---|---|---|---|---|---|---|---|
| ODI | coin | 186 | 0.538 | 0.693 | 0.250 | 0.500 | 0.000 | 0.000 | 0.000 |
| ODI | elo_only | 186 | 0.737 | 0.559 | 0.188 | 0.795 | 0.713 | 0.721 | 0.717 |
| ODI | logistic | 186 | 0.720 | 0.587 | 0.196 | 0.778 | 0.713 | 0.663 | 0.687 |
| ODI | random_forest | 186 | 0.731 | 0.567 | 0.191 | 0.775 | 0.700 | 0.733 | 0.716 |
| ODI | grad_boosting | 186 | 0.694 | 0.621 | 0.208 | 0.755 | 0.671 | 0.663 | 0.667 |
| ODI | xgboost | 186 | 0.699 | 0.591 | 0.200 | 0.768 | 0.670 | 0.686 | 0.678 |
| ODI | logistic_squad | 186 | 0.710 | 0.602 | 0.202 | 0.765 | 0.700 | 0.651 | 0.675 |
| ODI | logistic_by_format | 186 | 0.737 | 0.594 | 0.193 | 0.792 | 0.723 | 0.698 | 0.710 |
| ODI | random_forest_by_format | 186 | 0.731 | 0.566 | 0.190 | 0.775 | 0.705 | 0.721 | 0.713 |
| T20 | coin | 279 | 0.455 | 0.693 | 0.250 | 0.500 | 0.000 | 0.000 | 0.000 |
| T20 | elo_only | 279 | 0.609 | 0.622 | 0.217 | 0.708 | 0.648 | 0.618 | 0.633 |
| T20 | logistic | 279 | 0.663 | 0.616 | 0.214 | 0.710 | 0.667 | 0.763 | 0.712 |
| T20 | random_forest | 279 | 0.649 | 0.613 | 0.212 | 0.715 | 0.650 | 0.770 | 0.705 |
| T20 | grad_boosting | 279 | 0.642 | 0.616 | 0.214 | 0.712 | 0.648 | 0.750 | 0.695 |
| T20 | xgboost | 279 | 0.656 | 0.610 | 0.210 | 0.724 | 0.654 | 0.783 | 0.713 |
| T20 | logistic_squad | 279 | 0.663 | 0.598 | 0.207 | 0.736 | 0.667 | 0.763 | 0.712 |
| T20 | logistic_by_format | 279 | 0.631 | 0.633 | 0.221 | 0.685 | 0.652 | 0.691 | 0.671 |
| T20 | random_forest_by_format | 279 | 0.677 | 0.621 | 0.216 | 0.712 | 0.665 | 0.822 | 0.735 |

## How many runs will the team batting first score?

Lower MAE/RMSE is better; R2 is relative to predicting the test mean.

| model | n | mae | rmse | r2 |
|---|---|---|---|---|
| baseline_format_mean | 456 | 44.242 | 58.262 | 0.478 |
| baseline_venue_mean | 456 | 43.181 | 58.184 | 0.480 |
| ridge | 456 | 40.472 | 53.188 | 0.565 |
| grad_boosting | 456 | 44.779 | 59.871 | 0.449 |

By format:

| scope | model | n | mae | rmse | r2 |
|---|---|---|---|---|---|
| ODI | baseline_format_mean | 181 | 65.681 | 79.282 | -0.063 |
| ODI | baseline_venue_mean | 181 | 65.165 | 80.463 | -0.095 |
| ODI | ridge | 181 | 59.247 | 71.876 | 0.126 |
| ODI | grad_boosting | 181 | 65.713 | 81.061 | -0.111 |
| T20 | baseline_format_mean | 275 | 30.132 | 38.620 | -0.007 |
| T20 | baseline_venue_mean | 275 | 28.712 | 36.774 | 0.087 |
| T20 | ridge | 275 | 28.114 | 35.927 | 0.129 |
| T20 | grad_boosting | 275 | 31.000 | 40.238 | -0.093 |

Paired bootstrap of the error reduction (positive = model beats the baseline):

| scope | model | vs | mae_gain | ci_low | ci_high | better_significantly |
|---|---|---|---|---|---|---|
| all | ridge | baseline_format_mean | 3.771 | 1.060 | 6.404 | True |
| all | ridge | baseline_venue_mean | 2.709 | -0.265 | 5.718 | False |
| all | grad_boosting | baseline_format_mean | -0.536 | -3.536 | 2.432 | False |
| all | grad_boosting | baseline_venue_mean | -1.597 | -5.034 | 1.755 | False |
| ODI | ridge | baseline_format_mean | 6.434 | 0.827 | 12.200 | True |
| ODI | ridge | baseline_venue_mean | 5.918 | -0.335 | 12.430 | False |
| ODI | grad_boosting | baseline_format_mean | -0.032 | -7.199 | 7.079 | False |
| ODI | grad_boosting | baseline_venue_mean | -0.548 | -8.128 | 7.304 | False |
| T20 | ridge | baseline_format_mean | 2.018 | -0.433 | 4.439 | False |
| T20 | ridge | baseline_venue_mean | 0.598 | -2.016 | 3.265 | False |
| T20 | grad_boosting | baseline_format_mean | -0.868 | -2.753 | 1.043 | False |
| T20 | grad_boosting | baseline_venue_mean | -2.288 | -4.779 | 0.275 | False |

Note: the pooled R2 is inflated because ODI and T20 scores differ by ~100 runs; read the per-format rows.

## Saved models

* `models/winner_logistic.joblib`
* `models/winner_elo_logistic.joblib`
* `models/score_ridge.joblib`

## Limits

* About 640 decided matches in total: small data, so differences of a point or two in accuracy are noise (see the intervals).
* Outcomes of a single cricket match are close to a coin flip even for strong models; the realistic goal is calibrated probabilities slightly better than Elo.
* Team features are team-level only. Squad, pitch, weather and day/night are not modelled (not collected).
