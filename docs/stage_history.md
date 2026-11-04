# Stage-by-stage build log (original README)

> Kept for reference. The current overview is in the repository README.

Men's ICC **ODI** and **T20** World Cup historical data engineering and analytics platform (tournament editions **2003–2026**).

**Status:** Stage 13 — Python analytics on dbt marts.  
Leaderboards, team records, venue averages, and BBB-derived rates (complete matches only) write to `data/processed/analytics/`. Coverage is never claimed complete.

---

## 1. Project overview

This project builds a local, free-stack platform to:

1. Register in-scope World Cup editions  
2. Discover matches from ESPNcricinfo (primary source)  
3. Collect scorecards and ball-by-ball commentary where available  
4. Validate, warehouse, and analyze the data  
5. Present interactive analytics in Streamlit  

**Rules:** never fabricate missing records; never claim complete coverage without a verified coverage report; respect source terms and robots.txt.

---

## 2. Tournament scope (16 editions only)

| Format | Years |
|--------|-------|
| Men's ODI World Cup | 2003, 2007, 2011, 2015, 2019, 2023 |
| Men's T20 World Cup | 2007, 2009, 2010, 2012, 2014, 2016, 2021, 2022, 2024, 2026 |

Excluded: women's World Cups, Champions Trophy, U19, qualifiers, bilaterals, domestic cricket.

There is **no** 2002 World Cup edition.  
`T20_M_2026` is registered as **completed** (India beat New Zealand, final 8 March 2026) based on public ICC / ESPNcricinfo / Reuters reports. Match-level collection has not started.

Registry file: `config/tournaments.yaml` (validated by `src/discovery/tournament_registry.py`)

---

## 3. Architecture (target)

```text
ESPNcricinfo
     |
Tournament Registry → Match Discovery → Match URL Manifest
     |
Historical Collection (scorecards + commentary)
     |
Raw JSON → Parse/Normalize → Data Quality → PostgreSQL
     |
DuckDB + Parquet → dbt → Analytics → Streamlit
```

---

## 4. Technology stack

| Layer | Tools |
|-------|--------|
| Collection | Python 3.12+, Requests, BeautifulSoup4, Playwright (optional), Tenacity |
| Storage | PostgreSQL, DuckDB, Parquet, JSON |
| Engineering | SQL, dbt Core, Pydantic, Pandas |
| Analytics | Pandas, NumPy, SciPy, DuckDB SQL, Plotly |
| Dashboard | Streamlit |
| Dev | pytest, Ruff, Docker Compose (optional) |

No paid APIs or OpenAI keys required.

---

## 5. Installation (Stage 1)

### Prerequisites

- Python **3.12+**
- Git (optional)
- Docker Desktop (optional, for PostgreSQL)

### Setup

```powershell
cd "c:\Users\DELL\Downloads\icc world cups anaylsis\cricket-worldcup-analytics"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env
```

### Bootstrap

```powershell
python scripts/initialize_database.py
python scripts/discover_tournaments.py
```

These commands validate the 16-tournament registry (Pydantic), ensure data directories exist, and sync `data/manifests/tournaments.csv`.  
PostgreSQL schema creation arrives in **Stage 3**.

### PostgreSQL via Docker

Host port **5433** is used (avoids conflict with a local Postgres on 5432).

```powershell
docker compose up -d postgres
python scripts/initialize_database.py
# or apply migrations only:
python scripts/run_migrations.py
```

This creates all 16 required tables and seeds `sources` + 16 `tournaments` rows (no fabricated matches).

### Optional: Streamlit (registry view only)

```powershell
streamlit run app/dashboard.py
```

---

## 6. Environment configuration

Copy `.env.example` → `.env` and adjust:

- `DATABASE_URL` / Postgres credentials  
- `DUCKDB_PATH`  
- `HTTP_REQUEST_DELAY_SECONDS` (keep conservative)  
- `RESPECT_ROBOTS_TXT=true`  
- `ENABLE_PLAYWRIGHT=false` until needed  

Secrets must stay out of git (`.env` is gitignored).

---

## 7. Implementation stages

| Stage | Focus | Status |
|------:|-------|--------|
| 1 | Project initialization | **Done** |
| 2 | Configuration & tournament registry | **Done** |
| 3 | Database schema & migrations | **Done** |
| 4 | Tournament discovery (live) | **Done** |
| 5 | Match discovery | **Done** |
| 6 | Scorecard collection | **Done** |
| 7 | Commentary / ball-by-ball collection | **Done** |
| 8 | Parse / normalize → `data/processed` | **Done** |
| 9 | Dataset validation | **Done** |
| 10 | Pipeline + PostgreSQL load | **Done** |
| 11 | DuckDB / Parquet warehouse | **Done** |
| 12 | dbt models (staging / marts) | **Done** |
| 13 | Python analytics on marts | **Done** |
| 14–15 | Dashboard, dataset export | Pending |
| 16–18 | Testing, docs, E2E validation | Pending |

---

## 8. Ball-by-ball collection (Stage 7)

```powershell
# Prefer Cricsheet (complete) + ESPN commentary (partial) for a tournament sample
python scripts/collect_commentary.py --tournament ODI_M_2023 --limit 3 --source both

# Cricsheet only (downloads WC JSON zip from cricsheet.org/downloads/)
python scripts/collect_commentary.py --tournament ODI_M_2023 --source cricsheet

# ESPN commentary HTML only (usually a recent-ball window → status=partial)
python scripts/collect_commentary.py --match 1384392 --source espn
```

Outputs per match under `data/raw/commentary/<match_id>/`:

- `deliveries_cricsheet.json` — complete BBB when date+teams uniquely match
- `commentary_espn.json` / `commentary.html` — partial ESPN window when fetched
- `bbb_status.json` — combined status (`complete` | `partial` | `unavailable` | `not_checked`)

Ambiguous Cricsheet date/team matches are **refused** (no silent merge). ESPN 401/403/429 stops further ESPN fetches.

## 9. Normalize collected data (Stage 8)

```powershell
# Build processed entity bundles for matches that already have scorecard.json
python scripts/normalize_collected.py --tournament ODI_M_2023

python scripts/normalize_collected.py --match 1384392 --force
```

Writes:

- `data/processed/matches/<match_id>.json` — match + teams + players + innings + scorecards
- `data/processed/innings|deliveries|players/<match_id>.json`
- `data/processed/teams/teams.json` — cumulative team registry

Toss choices are mapped (`1→bat`, `2→field`). Players are never merged by name alone. Missing BBB stays `not_checked` / `unavailable` — deliveries are not invented.

## 10. Validate dataset (Stage 9)

```powershell
python scripts/validate_dataset.py --tournament ODI_M_2023
python scripts/validate_dataset.py --match 1384392
```

Checks include: required match fields, batting+extras vs innings totals, BBB run sums vs innings (when `complete`), player source-identity uniqueness, and coverage gaps. Exit code `1` if any **errors** (warnings/info still exit `0`).

Outputs:

- `data/processed/validation/validation_report_<tournament|all>.json`
- `data/processed/validation/validation_issues_<tournament|all>.csv`
- `data/processed/validation/coverage_<tournament|all>.json` (`claims_complete_coverage: false`)

## 11. Pipeline & DB load (Stage 10)

```powershell
# Normalize + validate + load already-collected tournament data
python scripts/run_pipeline.py --tournament ODI_M_2023

# Load only
python scripts/load_processed.py --tournament ODI_M_2023

# Dry-run load targeting
python scripts/load_processed.py --tournament ODI_M_2023 --dry-run

# Optional: also collect before normalize (network)
python scripts/run_pipeline.py --tournament ODI_M_2023 --collect --source cricsheet
```

Cricsheet delivery player names are stored as `cricsheet_*` player ids (not merged onto ESPN ids by name).

## 12. DuckDB / Parquet warehouse (Stage 11)

```powershell
# Full warehouse mirror (all Postgres analytical tables)
python scripts/sync_warehouse.py --replace-duckdb

# Tournament-scoped slice (separate DuckDB + parquet/<tournament_id>/)
python scripts/sync_warehouse.py --tournament ODI_M_2023 --replace-duckdb

# Via pipeline
python scripts/run_pipeline.py --tournament ODI_M_2023 --stages warehouse
```

Outputs:

- `data/warehouse/cricket.duckdb` (full) or `cricket_<tournament_id>.duckdb` (scoped)
- `data/warehouse/parquet/*.parquet` or `parquet/<tournament_id>/`
- `data/warehouse/warehouse_manifest_<tournament|all>.json`

## 13. dbt models (Stage 12)

```powershell
# Build all models into data/warehouse/cricket.duckdb (schema analytics_*)
python scripts/run_dbt.py run
python scripts/run_dbt.py test

# Or against the ODI 2023 DuckDB file
python scripts/run_dbt.py run --target odi_2023
python scripts/run_dbt.py test --target odi_2023

# Optional tournament filter var
python scripts/run_dbt.py run --tournament ODI_M_2023
```

Key marts: `dim_matches`, `fct_deliveries`, `fct_innings`, `mart_tournament_summary`, `mart_batting_tournament_totals`, `mart_bowling_tournament_totals`.

## 14. Analytics (Stage 13)

```powershell
python scripts/run_analytics.py --tournament ODI_M_2023
python scripts/run_analytics.py --tournament ODI_M_2023 --json
```

Produces `data/processed/analytics/analytics_<tournament_id>.json` with batting/bowling leaders, team records, venue averages, and optional BBB phase/economy metrics (only when complete ball-by-ball exists).

## 15. Data source attribution

Primary source: **ESPNcricinfo**. Supplementary complete BBB: **Cricsheet** (WC JSON downloads; `/data/` paths are not used — robots disallow).

Users are responsible for complying with each source's terms of service, robots.txt, and copyright. See `config/source_rules.yaml` and `LICENSE`.

---

## 16. Historical coverage limitations

- Older tournaments may lack full ball-by-ball commentary.  
- Some matches may be abandoned, tied, DLS-affected, or Super Over.  
- `number_of_matches` and winners are **not** hardcoded until verified.  
- Coverage reports will reflect **collected** data only.

---

## 17. Troubleshooting (Stage 1)

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: src` | Run commands from project root; `pythonpath` is set in `pyproject.toml` for pytest |
| YAML load errors | Ensure `config/*.yaml` files are present and valid |
| Docker port 5432 in use | Project defaults to host **5433** — see `.env` / `docker-compose.yml` |
| `password authentication failed for user cricket` | Ensure you are using the Docker Compose DB on port 5433, not another local Postgres |
| Tournament discovery `access_restricted` / HTTP 403 | ESPNcricinfo is blocking automated requests. The pipeline records the failure and stops; it will not bypass CAPTCHA/WAF. Retry later from an allowed network or use cached raw HTML if you obtained pages through permitted means. |
| pip / venv issues | Confirm `python --version` is 3.12+ |

---

## 18. License

MIT for the software. Third-party cricket data remains owned by its rights holders.

---

## Stage 2 — Data profiling and audit (read-only)

```powershell
python scripts/run_profiling.py          # writes reports/ only; changes no data
```

Outputs in `reports/`: `data_inventory.csv`, `data_profile.html`, `missing_values_report.csv`,
`duplicate_records_report.csv`, `relationship_report.csv`, `data_quality_audit.md`, plus
`tournament_coverage.csv` and `duplicate_player_identities.csv`. All numbers are computed from the
live database and files; re-run to refresh. Code: `src/profiling/`.

**Safety note:** `match_urls.csv` is rebuilt from `data/raw/matches/*/discovered_matches.json` if it
is ever lost. Manifest syncing is atomic and preserves later-stage columns (regression test:
`tests/test_manifest_sync.py`).

## Stage 3 — Data quality framework

```powershell
python scripts/run_data_quality.py            # writes reports/data_quality_report.md + reports/data_quality/
python scripts/run_data_quality.py --persist  # also refreshes data_quality_results (only its own dq_rule rows)
```

~130 declarative rules (`src/validation/validate_*.py`, engine in `rules.py`) check completeness, uniqueness,
validity, referential integrity, consistency and historical coverage per tournament. Scores are severity-weighted
pass rates; the method is documented in the report. The older per-match bundle validators
(`match_validation.py` etc.) still run in the pipeline; this layer validates the loaded database.

Note: `deliveries.over_number` is 1-based, and `legal_ball_number` numbers no-balls (balls faced), so it is **not**
balls bowled — compute overs from `is_wide` / `is_no_ball`.

---

## Stage 4 — Bronze / silver / gold layers

```powershell
python scripts/build_lakehouse.py --layer all     # bronze -> silver -> gold (about 1 minute)
python scripts/build_lakehouse.py --verify        # re-hash bronze against its manifest
```

* **Bronze** (`data/bronze/`, `src/ingestion/bronze.py`): immutable, versioned Parquet snapshots of the collected
  files with provenance columns. A run writes a new `batch_id=` folder, never overwrites, skips if unchanged, and
  logs SHA-256 hashes in `_manifest.json`.
* **Silver** (`data/silver/`, `src/transformations/silver.py`, `identity.py`): cleaned and conformed. Resolves the
  Cricsheet player names to ESPN ids **per match, against that match's roster** (99.8% of names, validated against
  scorecards), repairs alias team ids, fills tie-break winners, parses result text (margin, DLS, walkover), builds a
  real stage taxonomy, derives missing Super Over totals, and numbers true legal deliveries.
* **Gold** (`data/gold/`, `src/transformations/gold.py`): dimensions, facts and marts with consistent metric
  definitions (documented at the top of the module). Ball-by-ball metrics are null where no ball-by-ball exists.

Silver and gold are derived and safe to delete and rebuild; bronze is the preserved record.
Super Overs live in `fact_super_over_performances` and are excluded from regular statistics.

## Stages 5 & 6 - analytical database and warehouse load

```bash
python scripts/load_warehouse.py                    # gold -> Postgres `analytics` + DuckDB (+ DDL + design doc)
python scripts/run_data_quality.py --layer gold --persist   # quality rules on the resolved data
python scripts/run_migrations.py                    # Alembic: revision 20261103_0002 creates the schema
```

* Design: [docs/database_design.md](docs/database_design.md) (generated); DDL: `sql/schema/analytics_schema.sql`.
* Postgres `public` = as-collected tables; Postgres `analytics` = star schema (5 dimensions, 6 facts,
  7 marts) with primary keys, foreign keys, checks and indexes; DuckDB `data/warehouse/cricket_gold.duckdb` = full copy.
* Loads are incremental and idempotent (`INSERT .. ON CONFLICT .. WHERE row differs`, one transaction);
  a re-run on unchanged gold changes 0 rows. Per-table counts are logged in `analytics.load_audit`.
* Gold quality report: `reports/gold/data_quality_report.md` (22 rules, results persisted as `dq_rule_gold`).

## Stages 7 & 8 - dbt on gold and SQL analytics

```bash
dbt build --project-dir dbt_gold --profiles-dir dbt_gold      # 5 analytics models + 46 tests (run from repo root)
dbt test  --project-dir dbt_gold --profiles-dir dbt_gold --select source:gold   # 36 key/FK tests on gold
python scripts/run_sql_analytics.py                           # 40 queries -> reports/sql_analytics/*.csv + INDEX.md
```

* `dbt_gold/` is separate from `dbt/` (which models the as-collected tables). It needs a dbt whose DuckDB
  matches the one that wrote `cricket_gold.duckdb` (system Python: duckdb 2.0); the `.venv` copy is older.
* Query library: `sql/analytics/queries.sql` (batting, bowling, teams, matches, tournaments, venues, phases,
  window-function analyses). ODI data starts at 2003, so career figures cover 2003-2023 only.

## Stages 9 & 10 - EDA notebooks and statistical tests

```bash
python scripts/build_notebooks.py        # builds + executes notebooks/01..03 from the gold DuckDB
python scripts/run_statistical_tests.py  # 20 hypothesis tests -> reports/statistical_tests.md/.csv
```

* Notebooks: tournaments and matches, batting and bowling, phases and venues. Findings are printed by
  code, so they always match the data.
* Tests (`src/analytics/stats_tests.py`): toss, batting first, scoring/sixes trends, chase vs target,
  venue and host effects, phase dot-ball shares. Each reports an effect size, a 95% interval and a
  Holm-corrected p-value. Matches are not independent draws, so p-values are indicative.

## Stages 11 & 12 - features and models

```bash
python scripts/build_features.py   # -> data/features/match_features.parquet + docs/feature_catalog.md
python scripts/train_models.py     # expanding-window evaluation -> reports/ml_report.md, models/*.joblib
```

* Features use only matches on strictly earlier dates (same-day matches are isolated); `tests/test_features.py`
  rewrites the future and checks earlier features do not move. Catalog: [docs/feature_catalog.md](docs/feature_catalog.md).
* Models are scored by an expanding window over tournaments (train on earlier editions, test on the next),
  against baselines, with paired-bootstrap intervals. A label-shuffle test guards against leakage.
* Results and limits: [reports/ml_report.md](reports/ml_report.md).

## Stages 13 & 14 - interpretability and dashboard

```bash
python scripts/explain_models.py          # reports/interpretability.md, importance/SHAP CSVs, reports/figures/
streamlit run app/dashboard.py            # 9-page dashboard on the gold DuckDB
```

* Interpretability: out-of-time permutation importance, SHAP (additive, tested), feature-set ablation
  (the Elo gap alone is as good as all 13 features) and per-match explanations.
* Dashboard pages: home, tournaments, matches, players, teams, ball-by-ball, historical records (the SQL
  library, live), data coverage, win predictor (Elo baseline), model insights. Synthetic fields are
  always labelled. Every page is exercised headlessly by `tests/test_dashboard.py`.

## Stages 15-18 - pipeline, report, tests, docs

```bash
python scripts/run_lakehouse_pipeline.py            # bronze -> gold -> warehouse -> quality gate -> dbt -> analytics -> ML -> report
python scripts/run_lakehouse_pipeline.py --dry-run  # plan only; --from/--to/--only/--skip select steps; --with synthetic
python scripts/build_docs.py                        # docs/data_dictionary.md from the live schema
python -m pytest tests -q                           # full suite
```

* The pipeline stops at the first failure or failed gate (bronze intact, Postgres counts match gold, no critical
  data-quality failure beyond documented residuals) and records every run in `reports/pipeline_run.json`.
* Executive report: [reports/executive_report.md](reports/executive_report.md) (built from the outputs, no typed numbers).
* Docs: [architecture](docs/architecture.md), [data dictionary](docs/data_dictionary.md),
  [database design](docs/database_design.md), [feature catalog](docs/feature_catalog.md),
  [synthetic data](docs/synthetic_data.md).

## Brief-compliance additions (dashboard, models, reports)

* **Dashboard** (`streamlit run app/dashboard.py`): home KPIs (tournaments, matches, teams, players, runs, wickets,
  data-quality score, ball-by-ball coverage) and eight pages: Tournament Explorer, Player Analytics (comparison,
  consistency, clustering), Team Analytics, Match Analytics, Ball-by-Ball Analytics (incl. live first-innings
  projection), Statistical Research, Machine Learning (winner and score predictors with explanations), Data
  Engineering (pipeline, freshness, inventory, quality, missing data, lineage), plus Historical Records.
* **Models 1-5**: winner (logistic, random forest, gradient boosting, XGBoost, squad features, per-format pipelines),
  live innings projection, batting-performance regression, player clustering, consistency.
* **Reports**: `data_quality`, `data_engineering`, `exploratory_analysis`, `statistical_analysis`, `machine_learning`,
  `cricket_insights` (each with the ten required sections) in `reports/`; model outputs in `reports/model_evaluation`,
  `feature_importance`, `shap_analysis`, `model_comparison`.
* `python scripts/run_lakehouse_pipeline.py` rebuilds all of it (18 steps).

## React dashboard (modern UI, per-World-Cup themes)

The original Streamlit app (`app/`) is kept; a React front end now renders the **same pages, charts, tables and
filters** with a new design.

```bash
python scripts/run_react_dashboard.py --build   # first time: installs and builds the front end (Node 18+)
python scripts/run_react_dashboard.py           # then just this -> http://localhost:8000
```

How it works
- `server/stshim.py` is a small stand-in for the `streamlit` module. The page scripts in `app/pages/*.py` run unchanged;
  every `st.*` call (tabs, columns, metrics, Plotly figures, tables, widgets) is recorded as JSON.
  Nothing is re-implemented, so the React app cannot drift from the Streamlit pages (192 charts, 11 pages, every tab).
- `server/api.py` (FastAPI): `GET /api/meta` (editions, logos, themes, Plotly template), `POST /api/page/{slug}`
  (widget state + selected World Cup -> UI tree). Results are cached; start-up pre-runs every page.
- `web/` (React + Vite + Plotly.js): renders the tree. `npm run dev` in `web/` gives hot reload (API on port 8000).

World Cup filter and themes
- 16 logos in `web/public/logos/`; the rail at the top selects an edition (click a logo on the Home gallery to open it).
- The whole site is re-coloured from the selected logo (`server/editions.py`) and the Plotly charts are re-coloured to match.
- The selection sets the page filters: Tournaments / Squads (format and year), Matches (tournament), match pickers
  (narrowed to that tournament's dates), format switches elsewhere. Pages that are not edition-specific (for example
  Players, Teams, Data Engineering) keep showing all editions and only take the theme.
- If an edition has no rows for a match picker (for example no ball-by-ball for T20 2007), a note says so.

Tests: `tests/test_react_backend.py` (runs in a subprocess so the shim cannot affect the Streamlit tests).

React dashboard details: result tables list `match_id` as a hidden column, so any row with one is clickable and opens the
match on the Match Analytics page (the page reads `st.session_state["focus_match"]`). The ICC logo is in `web/public/icc-logo.png`.
The React app does not show the "synthetic demo data" banner or the synthetic marker columns (the Streamlit app still does);
the pitch/weather/day-night values remain generated placeholders, see `docs/synthetic_data.md`.

## Champions Trophy and Test Championship

The React dashboard has a competition switcher: World Cups / Champions Trophy (7 editions, 2002-2025) / Test Championship
(3 completed cycles and the 2025-27 cycle in progress) / ICC Men's Cricket World Cup 2027 (upcoming: schedule, venues, teams,
qualification; no results exist yet). Each has its own database (same tables), logos, colours, pages
and a Statistics page. Build the data with `python scripts/run_competitions.py` (needs internet the first time; ESPNcricinfo
pages are fetched politely and cached). Sources, checks, coverage and design are in `docs/competitions.md`.
