# Statistical tests (Stage 10)

20 hypothesis tests on the gold layer. p-values are corrected for the whole family with Holm's method; a result is called significant only if the corrected p < 0.05.

**How to read this.** Matches are not independent draws (the same teams and tournaments repeat), so p-values are indicative. With large samples tiny effects become significant, so the effect size and interval matter more than the verdict.

| Test | n | Effect | 95% CI | p | p (Holm) | Verdict |
|---|---|---|---|---|---|---|
| `toss_win_rate_ODI` | 285 | toss winner win rate: 0.481 | 0.423 to 0.539 | 0.554 | 1.000 | cannot reject H0 |
| `toss_win_rate_T20` | 357 | toss winner win rate: 0.515 | 0.464 to 0.567 | 0.597 | 1.000 | cannot reject H0 |
| `bat_first_win_rate_ODI` | 285 | bat-first win rate: 0.540 | 0.482 to 0.597 | 0.192 | 1.000 | cannot reject H0 |
| `bat_first_win_rate_T20` | 357 | bat-first win rate: 0.507 | 0.455 to 0.559 | 0.832 | 1.000 | cannot reject H0 |
| `bat_first_trend_ODI` | 285 | odds ratio per year: 0.993 | 0.959 to 1.027 | 0.665 | 1.000 | cannot reject H0 |
| `bat_first_trend_T20` | 357 | odds ratio per year: 0.994 | 0.962 to 1.027 | 0.715 | 1.000 | cannot reject H0 |
| `toss_decision_ODI` | 285 | Cramer's V: 0.082 |  | 0.207 | 1.000 | cannot reject H0 |
| `toss_decision_T20` | 357 | Cramer's V: 0.022 |  | 0.765 | 1.000 | cannot reject H0 |
| `scoring_trend_ODI` | 265 | runs per year: 3.032 | 1.733 to 4.330 | <0.001 | <0.001 | reject H0 |
| `scoring_trend_T20` | 340 | runs per year: 0.251 | -0.363 to 0.864 | 0.422 | 1.000 | cannot reject H0 |
| `chase_vs_target_ODI` | 265 | odds ratio per +10 runs of target: 0.755 | 0.705 to 0.807 | <0.001 | <0.001 | reject H0 |
| `chase_vs_target_T20` | 340 | odds ratio per +10 runs of target: 0.685 | 0.624 to 0.753 | <0.001 | <0.001 | reject H0 |
| `venue_effect_ODI` | 85 | epsilon-squared: 0.231 |  | 0.054 | 0.599 | cannot reject H0 |
| `venue_effect_T20` | 287 | epsilon-squared: 0.255 |  | <0.001 | <0.001 | reject H0 |
| `host_advantage_ODI` | 78 | host win rate: 0.705 | 0.596 to 0.795 | <0.001 | 0.005 | reject H0 |
| `host_advantage_T20` | 63 | host win rate: 0.603 | 0.480 to 0.715 | 0.130 | 1.000 | cannot reject H0 |
| `dot_ball_phase_ODI` | 141,245 | Cramer's V: 0.160 |  | <0.001 | <0.001 | reject H0 |
| `dot_ball_phase_T20` | 52,492 | Cramer's V: 0.153 |  | <0.001 | <0.001 | reject H0 |
| `sixes_trend_ODI` | 289 | rate ratio per year: 1.044 | 1.037 to 1.050 | <0.001 | <0.001 | reject H0 |
| `sixes_trend_T20` | 363 | rate ratio per year: 1.020 | 1.014 to 1.025 | <0.001 | <0.001 | reject H0 |

## Hypotheses and notes

**`toss_win_rate_ODI`** - H0: ODI: the toss winner wins the match 50% of the time. Method: exact binomial test vs 0.5. Toss is random, so a rate away from 50% would mean the toss carries real value.

**`toss_win_rate_T20`** - H0: T20: the toss winner wins the match 50% of the time. Method: exact binomial test vs 0.5. Toss is random, so a rate away from 50% would mean the toss carries real value.

**`bat_first_win_rate_ODI`** - H0: ODI: teams batting first win 50% of matches. Method: exact binomial test vs 0.5. Includes DLS-affected matches; see the sensitivity test for the target size.

**`bat_first_win_rate_T20`** - H0: T20: teams batting first win 50% of matches. Method: exact binomial test vs 0.5. Includes DLS-affected matches; see the sensitivity test for the target size.

**`bat_first_trend_ODI`** - H0: ODI: the bat-first win probability does not change with year. Method: logistic regression, Wald test on the year slope. Odds ratio below 1 means batting first has become less successful over time.

**`bat_first_trend_T20`** - H0: T20: the bat-first win probability does not change with year. Method: logistic regression, Wald test on the year slope. Odds ratio below 1 means batting first has become less successful over time.

**`toss_decision_ODI`** - H0: ODI: toss winners win equally often whether they bat or field. Method: chi-square test of independence (Fisher exact if a cell is empty). win rate when choosing bat 52.1% (n=146), field 43.9% (n=139)

**`toss_decision_T20`** - H0: T20: toss winners win equally often whether they bat or field. Method: chi-square test of independence (Fisher exact if a cell is empty). win rate when choosing bat 52.9% (n=138), field 50.7% (n=219)

**`scoring_trend_ODI`** - H0: ODI: first-innings totals do not change with year. Method: OLS regression slope (runs per year); Spearman rho as a robustness check. R2=0.074; Spearman rho=0.26 (p=1.29e-05); DLS-affected matches excluded because their first innings can be shortened.

**`scoring_trend_T20`** - H0: T20: first-innings totals do not change with year. Method: OLS regression slope (runs per year); Spearman rho as a robustness check. R2=0.002; Spearman rho=0.10 (p=0.0616); DLS-affected matches excluded because their first innings can be shortened.

**`chase_vs_target_ODI`** - H0: ODI: the chasing side's win probability does not depend on the target. Method: logistic regression, Wald test (target in units of 10 runs). A strongly negative slope is the expected sanity check: bigger targets are harder.

**`chase_vs_target_T20`** - H0: T20: the chasing side's win probability does not depend on the target. Method: logistic regression, Wald test (target in units of 10 runs). A strongly negative slope is the expected sanity check: bigger targets are harder.

**`venue_effect_ODI`** - H0: ODI: first-innings totals have the same distribution at every ground. Method: Kruskal-Wallis across 12 grounds with >= 6 matches. Not adjusted for year or team strength, so part of the effect is era, not ground.

**`venue_effect_T20`** - H0: T20: first-innings totals have the same distribution at every ground. Method: Kruskal-Wallis across 28 grounds with >= 6 matches. Not adjusted for year or team strength, so part of the effect is era, not ground.

**`host_advantage_ODI`** - H0: ODI: host nations win 50% of their decided matches against non-hosts. Method: exact binomial test vs 0.5. Hosts are matched by country name in the tournament's host_country; confounded by team strength (hosts are often strong).

**`host_advantage_T20`** - H0: T20: host nations win 50% of their decided matches against non-hosts. Method: exact binomial test vs 0.5. Hosts are matched by country name in the tournament's host_country; confounded by team strength (hosts are often strong).

**`dot_ball_phase_ODI`** - H0: ODI: the share of dot balls is the same in every phase. Method: chi-square test of independence (phase x dot/non-dot). dot-ball share by phase: {'death': 0.376, 'middle': 0.509, 'powerplay': 0.639}. Huge n makes tiny gaps significant; see V.

**`dot_ball_phase_T20`** - H0: T20: the share of dot balls is the same in every phase. Method: chi-square test of independence (phase x dot/non-dot). dot-ball share by phase: {'middle': 0.328, 'death': 0.303, 'powerplay': 0.477}. Huge n makes tiny gaps significant; see V.

**`sixes_trend_ODI`** - H0: ODI: sixes per match do not change with year. Method: Poisson regression, Wald test on the year slope. Counts are per match (both innings); matches vary in length, so this is indicative.

**`sixes_trend_T20`** - H0: T20: sixes per match do not change with year. Method: Poisson regression, Wald test on the year slope. Counts are per match (both innings); matches vary in length, so this is indicative.
