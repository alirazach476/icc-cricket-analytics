# Feature catalog (Stage 11)

All features are computed from matches strictly before the match date (see `src/features/match_features.py`). Team A/B order is a deterministic hash of the match id.

| Feature | Meaning | Source |
|---|---|---|
| `elo_diff` | Elo rating of team A minus team B (per format, K=30, updated after decided matches) | team history |
| `win_rate_diff` | Shrunk win rate A minus B over all prior matches in the format | team history |
| `form_diff` | Shrunk win rate over each team's last 5 matches, A minus B | team history |
| `runs_for_diff` | Average runs scored per innings (shrunk to format mean), A minus B | team history |
| `runs_against_diff` | Average runs conceded per innings (shrunk), A minus B | team history |
| `h2h_rate_a` | Shrunk share of prior meetings (same format) won by A | pair history |
| `min_prior_matches` | Fewer prior matches of the two teams; says how reliable the history is | team history |
| `venue_avg_first_innings` | Shrunk average first-innings score at the ground in prior matches | venue history |
| `is_knockout` | Match is a knockout stage | known pre-match |
| `is_t20` | Format indicator | known pre-match |
| `year` | Tournament year (era effect: scores trend upward) | known pre-match |
| `toss_edge_a` | +1 A won toss, -1 B won, 0 unknown | known at toss |
| `toss_field` | Toss winner chose to field | known at toss |
| `bat_runs_for / bowl_runs_against` | Score model: batting side's average runs for and bowling side's runs against | team history |
| `bat_elo_diff` | Score model: Elo of the batting-first side minus the bowling side | team history |

## Deliberately excluded (would leak the outcome)

* scores, margins, winner, player of the match, any in-match statistic;
* player-level career tables built from the whole dataset (they include the match itself);
* standings points of the tournament as a whole (final tables include future matches);
* squads announced after the tournament start (unclear timing), so squad strength is not used.
