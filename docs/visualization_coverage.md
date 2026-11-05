# Visualisation coverage

Every chart is built with Plotly from aggregated gold-layer data (no raw ball-by-ball is sent to the browser except for
the one match being viewed). Charts that the data cannot support are omitted or marked, never faked.

**Cross-cutting requirements**

| Requirement | How it is met |
|---|---|
| Titles, axis labels, units, hover details | Every figure has a descriptive title and labelled axes; hover shows the underlying values |
| Download the data behind a chart | A **CSV** button on every chart (bottom right of the chart) exports the plotted values; every table also has a CSV button. Checked against all 230 charts of the World Cup pages (`web/src/chartData.js`) |
| Filters: edition | The logo rail filters every page to one tournament (or all) |
| Filters: format | ODI / T20 (World Cups), ODI (Champions Trophy), Test (Test Championship) radios and sliders |
| Filters: team | Team pickers on Team Analytics, Squads and the Tournament Explorer (**Team** filter) |
| Filters: player | Player search on Player Analytics; matchups in Ball by Ball |
| Filters: venue | Tournament Explorer (**Venue** filter on the innings charts) and the Venues tab of Match Analytics |
| Filters: match stage | Tournament Explorer (**Match stage** multi-select), the stage picker on the Results tab, and stage colours on the innings, margin and team-stage charts |
| Filters: date | Tournament Explorer (**From date / To date**); match pickers show the date of every match |
| Missing or insufficient data | Minimum-sample sliders (balls faced / bowled, balls in a matchup), "not enough data" messages instead of empty charts, and a warning when a filter leaves nothing |
| Stages distinguished | Group / first round, second stage (Super Six / Eight / Ten / 12), quarter-final, semi-final and final are separate categories wherever the source has them |
| Performance | Queries aggregate in DuckDB, pages are cached, default views are pre-built for the deployment, tables paginate ("show more"), only one match's deliveries are loaded at a time |

## Requirement by requirement

Page names are the dashboard's left menu; **tab > chart title** is where to find it.

### 1. Tournament overview
| Required | Where |
|---|---|
| Matches by edition and format | Home > *Matches played by edition and format* |
| Participating teams by edition | Home > *Participating teams by edition* |
| Tournament timeline | Home > *Champions timeline*, *When World Cup matches are played*, *Where the World Cups were played* |
| Matches and results by stage | Tournaments > Overview > *Matches by stage*; Standings > *Results by team* |
| Wins and win % by team | Teams > World Cup history > *Win % by edition*; Tournaments > Standings; Home > *Titles by team* |
| Standings table | Tournaments > Standings (table + *Points* chart + *Points across all groups* heatmap) |

### 2. Batting
| Required | Where |
|---|---|
| Top run scorers | Tournaments > Batting and bowling > *Top run scorers* |
| Runs by player and tournament (grouped bars) | Tournaments > Batting analytics > *Runs by player and tournament* |
| Average vs strike rate | Tournaments > Batting and bowling > *Batters: average vs strike rate* |
| Runs vs balls faced | Tournaments > Batting analytics > *Runs against balls faced* (minimum-balls filter) |
| Fours and sixes | Tournaments > Batting analytics > *Boundaries: fours and sixes* (stacked); Statistics > *Boundaries hit by team* |
| Centuries and half-centuries | Tournaments > Batting analytics > *Centuries and half-centuries* |
| Score distribution | Players > Batting detail > *Score distribution*; Tournaments > Statistics > *Distribution of innings totals* |
| Performance across editions | Tournaments > Batting analytics > *Batting average by edition*; Players > Batting detail > *Runs by tournament and stage* |
| Consistency | Players > Consistency (rolling average on *Every innings*, coefficient of variation, steadiest batters) |

### 3. Bowling
| Required | Where |
|---|---|
| Top wicket-takers | Tournaments > Batting and bowling > *Top wicket takers* |
| Wickets vs economy | Tournaments > Batting and bowling > *Bowlers: economy vs wickets* |
| Bowling average vs strike rate | Tournaments > Bowling analytics > *Bowling average against strike rate* |
| Economy by player and edition | Tournaments > Bowling analytics > *Economy rate by player and edition* (heatmap) |
| Overs, wickets, runs conceded | Tournaments > Bowling analytics > *Overs, runs conceded and wickets* |
| Distributions (box plots) | Tournaments > Bowling analytics > *Economy rate distribution by edition*, *Strike rate distribution by edition* |
| Wicket types | Players > Bowling detail > *Wickets by dismissal type*; Tournaments > Overview > *How wickets fell* (ball-by-ball matches) |

### 4. Teams
| Required | Where |
|---|---|
| Wins and win % | Teams > World Cup history; Tournaments > Standings |
| Scoring trends across editions | Teams > By stage and trend > *Average runs scored / conceded per innings, by edition* |
| Runs vs wickets lost | Tournaments > Statistics > *Run rate vs wickets lost* |
| Batting first vs chasing | Teams > Batting and bowling > *Wins by batting first vs chasing*; Matches > Batting first vs chasing |
| Successful chases by target | Matches > Batting first vs chasing > *Bat-first win rate by first-innings score band*; Statistical Research > *Share of chases won, by target size* |
| Radar (normalised only) | Teams > Comparison: scaled across teams with 10+ matches |
| Head-to-head | Teams > Head-to-head |
| Performance by stage | Teams > By stage and trend > *results by match stage* |

### 5. Matches and innings
Matches > Match explorer: the **match centre** (scoreboard, scorecards, worm, run rate, wickets by over, innings comparison,
required vs actual run rate for chases, partnerships, fall of wickets), toss decision vs result (*From toss to result*),
margin of victory (*Winning margin*, *Margin by stage*), first-innings distribution by format (*ODI vs T20*), first vs
second innings score (target vs final), and *Ties and DLS-affected matches by edition*. Super-over innings appear as
score-only lines in the scorecard (no player lines are stored for super overs); DLS results are labelled in the result.

### 6. Ball by ball
Ball by Ball: runs and wickets by over, cumulative score (*Run progression*), dot-ball % (by phase and by over), boundary %
(*Fours and sixes by over*), powerplay / middle / death comparison (format-appropriate phases), outcome mix (*What happens
on a ball*). **Matchups** tab: batter v bowler strike-rate heatmap and scatter, with a minimum-balls slider (6-30) so
small samples are left out.

### 7. Statistical research
Statistical Research: distributions and box plots, 95% intervals and error bars with n, effect-size plots, a correlation
matrix (with the caution that correlation is not causation), regression diagnostics (*Residuals of the trend line* and
*Residuals against fitted values*), historical trends, and **Stage comparison**: first-innings total and batting-first win
rate for group stage v second stage v knockout, with intervals and n.

### 8. Machine learning
Machine Learning: confusion matrix (*predicted vs actual*), ROC curves, **precision-recall curve**, model comparison,
permutation importance, SHAP (*Mean |SHAP|* and **SHAP dependence**), calibration, **predicted-probability distribution**,
**prediction-error distribution**, actual vs predicted first-innings score (live projection and the **pre-match score model**),
**error distribution of the score model**, and a **learning curve**.

### 9. Data engineering and quality
Data Engineering: rows by table and by bronze entity, coverage matrix by edition, missing-value heatmap, validation
failures, **duplicate records by table**, quality scorecards, bronze > silver > gold pipeline timeline, lineage diagram,
freshness table, and **pipeline run history** (processing time of every recorded run).

## What is limited, and why

- **Learning curve.** A classic curve (accuracy against training-set size) would need many re-fits. The chart instead shows the
  log loss on each held-out tournament in time order, so later points have more training history. It is noisy (8-60
  matches per point) and is labelled as such.
- **SHAP.** The dependence plots use the logistic winner model (exact linear SHAP). Tree-model SHAP is not computed, so there is
  no beeswarm summary; the global importance bar chart is provided instead. Both need `scripts/build_ml_diagnostics.py`
  to be re-run if the features or models change.
- **Pipeline run history** starts with the first recorded run and grows by one row per run (`reports/pipeline_run_history.csv`).
  Earlier runs were not recorded, so they cannot be shown.
- **Date and venue filters** exist on the Tournament Explorer. Elsewhere, edition, team and player filters and the match
  pickers (which search by team, stage, venue and result) are used instead.
- **Test Championship and Champions Trophy** have no stage detail beyond group / final where ESPNcricinfo gives none; stage
  charts show only the categories the data has.
- **Required vs actual run rate** needs a chase with ball-by-ball data and a known target (limited-overs matches only).
- **Machine learning for ODI/T20 score projection** is trained on World Cups only; the Champions Trophy and Test Championship
  have their own winner models (see `docs/competitions.md`).
- **Batter v bowler matchups** only show pairs with the chosen minimum balls (default 12); a handful of balls says nothing
  about who has the upper hand.
