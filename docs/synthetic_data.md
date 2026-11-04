# Synthetic match conditions (pitch, weather, day/night)

**These values are not real.** Real pitch, weather and day/night data was not collected, so
`analytics.synthetic_match_conditions` holds seeded random placeholders to exercise schemas,
dashboards and pipelines end to end.

* Generator: `src/synthetic/match_conditions.py` (v1.0, default seed 20260101);
  run `python scripts/generate_synthetic_conditions.py`, then `python scripts/load_warehouse.py`.
* Every row has `is_synthetic = true` (database CHECK), the generator version and the seed.
* Values depend only on match id, month and format, never on scores, winners or venue results, so they
  cannot leak outcomes. Deterministic per match id; adding matches never changes existing rows.
* Stored in `data/synthetic/` (not `data/gold/`); excluded from the real marts, statistical tests and
  ML features/reports. Any "effect" found in these columns is noise by construction.
* Columns: `day_night`, `start_hour_local`, `pitch_type` (batting_friendly / balanced / bowling_friendly /
  spin_friendly), `temperature_c`, `humidity_pct`, `cloud_cover_pct`, `wind_kmh`, `rain_probability_pct`,
  `dew_expected`.
* To replace with real data later: load the real values into the same columns, set `is_synthetic = false`
  by dropping the CHECK in a new migration, and bump the provenance fields.
