"""Run the full read-only audit and write the Stage 2 reports.

Writes only to ``reports/``. Never modifies raw, processed, warehouse or database data.
"""

from __future__ import annotations

import html
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from src.profiling.profile_cricket_data import profile_cricket
from src.profiling.profile_dataset import file_collection_row, inventory_row, profile_dataframe
from src.profiling.profile_relationships import (
    declared_foreign_keys,
    identity_checks,
    logical_relationships,
    warehouse_consistency,
)

logger = logging.getLogger(__name__)

SKIP_TABLES = {"alembic_version"}


# --------------------------------------------------------------------------- loading
def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for value in obj.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def _scalars(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if not isinstance(v, (list, dict))}


def _json_dir_frame(directory: Path, kind: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if "report" in path.name:
            continue
        try:
            obj = _read_json(path)
        except json.JSONDecodeError:
            continue
        if kind == "match_bundle" and isinstance(obj, dict):
            base = _scalars(obj)
            match = _scalars(obj.get("match") or {})
            rows.append({**match, **base})
        elif kind == "squads" and isinstance(obj, dict):
            for squad in obj.get("squads") or []:
                for player in squad.get("players") or []:
                    rows.append(
                        {
                            "tournament_id": obj.get("tournament_id"),
                            "team_id": squad.get("team_id"),
                            **_scalars(player),
                        }
                    )
        elif kind == "deliveries" and isinstance(obj, dict):
            for d in obj.get("deliveries") or []:
                rows.append({"match_id": obj.get("match_id"), **_scalars(d)})
        else:
            rows.extend(_records(obj))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- inventory
def _db_inventory(engine: Engine, match_map: dict[str, str]) -> tuple[list[dict], list[dict]]:
    profiles, rows = [], []
    insp = inspect(engine)
    for table in sorted(insp.get_table_names()):
        if table in SKIP_TABLES:
            continue
        with engine.connect() as conn:
            df = pd.read_sql(text(f'select * from "{table}"'), conn)
        pk = insp.get_pk_constraint(table).get("constrained_columns") or None
        prof = profile_dataframe(
            f"postgres.{table}",
            df,
            path="postgresql://(DATABASE_URL)",
            fmt="postgres table",
            key=pk,
            match_to_tournament=match_map,
        )
        profiles.append(prof)
        rows.append(inventory_row(prof))
        logger.info("profiled postgres.%s (%s rows)", table, len(df))
    return profiles, rows


def _file_inventory(root: Path, match_map: dict[str, str]) -> tuple[list[dict], list[dict]]:
    profiles, rows = [], []

    def add(name: str, df: pd.DataFrame, path: Path, fmt: str, key=None, note: str | None = None):
        prof = profile_dataframe(
            name, df, path=str(path), fmt=fmt, key=key, match_to_tournament=match_map, note=note
        )
        profiles.append(prof)
        rows.append(inventory_row(prof))
        logger.info("profiled %s (%s rows)", name, len(df))

    data = root / "data"
    for path in sorted((data / "manifests").glob("*.csv")):
        df = pd.read_csv(path, dtype=str, keep_default_na=True)
        key = (
            "match_id"
            if "match_id" in df.columns and path.stem == "match_urls"
            else ("tournament_id" if path.stem == "tournaments" else None)
        )
        add(f"manifest.{path.stem}", df, path, "csv", key=key)

    processed = data / "processed"
    for sub, kind, key in (
        ("matches", "match_bundle", "match_id"),
        ("innings", "records", "innings_id"),
        ("players", "records", None),
        ("deliveries", "deliveries", None),
        ("standings", "records", None),
        ("squads", "squads", None),
    ):
        d = processed / sub
        if d.exists():
            note = "flattened from per-match/per-tournament JSON" + (
                "; players repeat across matches" if sub == "players" else ""
            )
            add(
                f"processed.{sub}",
                _json_dir_frame(d, kind),
                d,
                "json (many files)",
                key=key,
                note=note,
            )
    for single in ("teams", "tournaments"):
        p = processed / single / f"{single}.json"
        if p.exists():
            add(
                f"processed.{single}",
                pd.DataFrame(_records(_read_json(p))),
                p,
                "json",
                key=f"{single[:-1]}_id",
            )

    parquet_dirs = (
        [data / "warehouse" / "parquet"]
        + sorted(d for d in (data / "warehouse" / "parquet").iterdir() if d.is_dir())
        if (data / "warehouse" / "parquet").exists()
        else []
    )
    for d in parquet_dirs:
        for path in sorted(d.glob("*.parquet")):
            label = f"parquet.{d.name + '.' if d.name != 'parquet' else ''}{path.stem}"
            add(label, pd.read_parquet(path), path, "parquet")

    # DuckDB: inventory only (rows/columns/types); contents mirror Postgres or are derived marts.
    import duckdb

    for db in sorted((data / "warehouse").glob("*.duckdb")):
        try:
            con = duckdb.connect(str(db), read_only=True)
            tables = con.execute(
                "select table_schema, table_name, table_type from information_schema.tables "
                "where table_schema not in ('information_schema','pg_catalog') order by 1,2"
            ).fetchall()
            for schema, tname, ttype in tables:
                cols = con.execute(
                    "select column_name, data_type from information_schema.columns where table_schema=? and table_name=? "
                    "order by ordinal_position",
                    [schema, tname],
                ).fetchall()
                n = int(con.execute(f'select count(*) from "{schema}"."{tname}"').fetchone()[0])
                rows.append(
                    {
                        "dataset_name": f"duckdb.{db.stem}.{schema}.{tname}",
                        "file_path": str(db),
                        "file_format": f"duckdb {ttype.lower()}",
                        "rows": n,
                        "columns": len(cols),
                        "column_names": "; ".join(c[0] for c in cols),
                        "data_types": "; ".join(f"{c[0]}:{c[1]}" for c in cols),
                        "missing_values": "",
                        "columns_with_missing": "",
                        "duplicate_records": "",
                        "duplicate_records_ignoring_keys": "",
                        "unique_identifiers": "",
                        "date_range": "",
                        "tournament_coverage": "",
                        "odi_tournaments": "",
                        "t20_tournaments": "",
                        "memory_mb": "",
                        "potential_issues": "",
                        "note": "inventory only (not column-profiled)",
                    }
                )
            con.close()
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "dataset_name": f"duckdb.{db.stem}",
                    "file_path": str(db),
                    "file_format": "duckdb",
                    "potential_issues": f"unreadable: {exc}",
                    "note": "",
                }
            )

    # Counted-only file collections.
    for name, rel, pattern, fmt in (
        ("raw.scorecards.json", "data/raw/scorecards", "*.json", "json"),
        ("raw.scorecards.html", "data/raw/scorecards", "*.html", "html"),
        ("raw.commentary.json", "data/raw/commentary", "*.json", "json"),
        ("raw.commentary.html", "data/raw/commentary", "*.html", "html"),
        ("raw.squads.html", "data/raw/squads", "*.html", "html"),
        ("raw.standings.html", "data/raw/standings", "*.html", "html"),
        ("raw.tournaments", "data/raw/tournaments", "*.*", "html/json"),
        ("raw.matches", "data/raw/matches", "*.json", "json"),
        ("processed.analytics", "data/processed/analytics", "*.json", "json"),
        ("processed.validation", "data/processed/validation", "*.*", "json/csv"),
        ("external.cricsheet_zip", "data/raw/commentary/cricsheet", "*.zip", "zip"),
    ):
        p = root / rel
        if p.exists():
            rows.append(file_collection_row(name, p, pattern, fmt=fmt))
    return profiles, rows


# --------------------------------------------------------------------------- findings
def build_findings(ctx: dict[str, Any]) -> list[dict[str, str]]:
    f: list[dict[str, str]] = []

    def add(sev: str, area: str, text_: str, evidence: str) -> None:
        f.append({"severity": sev, "area": area, "finding": text_, "evidence": evidence})

    ident = ctx["identity"]
    if ident["names_split_across_sources"]:
        add(
            "High",
            "Identity",
            "Players exist under two ID schemes (ESPN and Cricsheet-derived); ball-by-ball and scorecards cannot be joined per player until resolved.",
            f"{ident['names_split_across_sources']} names map to both an espn_ and a cricsheet_ id; "
            f"{ident['delivery_batters_with_cricsheet_id']} distinct delivery batters carry cricsheet ids; "
            + (
                f"none of the {ident['scorecard_batters_distinct']} scorecard batters share an id with a delivery batter. "
                if ident["delivery_and_scorecard_player_id_overlap"] == 0
                else f"only {ident['delivery_and_scorecard_player_id_overlap']} of {ident['scorecard_batters_distinct']} scorecard batters share an id with a delivery batter. "
            )
            + "Initial-vs-full-name variants (e.g. 'JM Bairstow' vs 'Jonny Bairstow') are not counted here and will add more.",
        )

    cov: pd.DataFrame = ctx["cricket"]["tournament_coverage"]
    gaps = cov[cov["completed_without_deliveries"] > 0]
    if len(gaps):
        missing = int(gaps["completed_without_deliveries"].sum())
        zero = cov[cov["completed_with_deliveries"] == 0]["tournament_id"].tolist()
        add(
            "High",
            "Coverage",
            f"{missing} completed matches have no ball-by-ball data.",
            "; ".join(
                f"{r.tournament_id}: {r.completed_with_deliveries}/{r.completed_matches}"
                for r in gaps.itertuples()
            )
            + (f". No ball-by-ball at all for: {', '.join(zero)}." if zero else ""),
        )

    for r in ctx["relationships"]:
        if r["status"] == "fail":
            add(
                "High",
                "Integrity",
                f"Relationship violated: {r['relationship']}",
                f"{r['violating_rows']} of {r['checked_rows']} rows. {r['detail']}"
                + (f" Examples: {r['examples']}" if r.get("examples") else ""),
            )
        elif r["status"] == "warn":
            add(
                "Medium",
                "Integrity",
                f"Relationship needs review: {r['relationship']}",
                f"{r['violating_rows']} of {r['checked_rows']} rows. {r['detail']}"
                + (f" Examples: {r['examples']}" if r.get("examples") else ""),
            )
        elif r["status"] == "error":
            add("Medium", "Audit", f"Check could not run: {r['relationship']}", r["detail"])

    for prof in ctx["profiles"]:
        if not prof["dataset"].startswith("postgres."):
            continue
        t = prof["dataset"].split(".", 1)[1]
        if prof["rows"] == 0:
            add("Medium", "Completeness", f"Table {t} is empty.", "0 rows")
            continue
        full = [c["column"] for c in prof["column_profiles"] if c["null_pct"] == 100]
        if full:
            add("Medium", "Completeness", f"{t}: columns that are entirely null.", ", ".join(full))
        part = [
            f"{c['column']} {c['null_pct']:.0f}%"
            for c in prof["column_profiles"]
            if 10 <= c["null_pct"] < 100
        ]
        if part:
            add(
                "Low",
                "Completeness",
                f"{t}: columns with substantial missing values.",
                ", ".join(part),
            )
        if prof["duplicate_keys"] or prof["duplicate_rows_ignoring_keys"]:
            add(
                "Medium",
                "Uniqueness",
                f"{t}: duplicate rows.",
                f"duplicate keys={prof['duplicate_keys']}, duplicates ignoring surrogate keys={prof['duplicate_rows_ignoring_keys']}",
            )

    if ident["teams_named_as_their_id"]:
        add(
            "Medium",
            "Consistency",
            "Teams without a real name (name equals id); they appear to be alias ids.",
            f"{ident['teams_named_as_their_id']}; never used as team1/team2, but referenced as winner or toss winner in "
            f"{ident['placeholder_team_references']} matches. Compare with the winner/toss examples above.",
        )
    if ident["short_names_not_uppercase_abbrev"]:
        add(
            "Low",
            "Consistency",
            "Team short names are inconsistent (some are full words).",
            ", ".join(ident["short_names_not_uppercase_abbrev"]),
        )
    vv = ctx["cricket"]["venue_variants"]
    if len(vv):
        add(
            "Medium",
            "Consistency",
            "Venue names that differ only by case/punctuation.",
            f"{len(vv)} groups, e.g. {vv.iloc[0]['names']}",
        )
    stages = ctx["cricket"]["stage_distribution"]
    other = int(stages.loc[stages["match_stage"] == "Other", "matches"].sum())
    if other:
        add(
            "Low",
            "Consistency",
            "Match stage 'Other' is ambiguous (pre-knockout rounds such as Super Six or quarterfinals).",
            f"{other} matches; needs a proper stage taxonomy before stage-based analysis",
        )
    add(
        "Low",
        "Modelling",
        "Venues are free text with no venue dimension, so venue analysis depends on string cleaning.",
        f"{ctx['cricket']['entity_counts']['venues_distinct_text']} distinct venue strings, "
        f"{ctx['cricket']['entity_counts']['cities_distinct_text']} cities",
    )
    return f


# --------------------------------------------------------------------------- writers
def _md_table(df: pd.DataFrame, max_rows: int = 60) -> str:
    if df.empty:
        return "_none_\n"
    df = df.head(max_rows).astype(object).where(df.head(max_rows).notna(), "")
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append(
            "| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ") for c in cols) + " |"
        )
    return "\n".join(lines) + "\n"


def write_audit_markdown(ctx: dict[str, Any], path: Path) -> None:
    cricket = ctx["cricket"]
    counts = cricket["entity_counts"]
    findings = pd.DataFrame(ctx["findings"])
    rel = pd.DataFrame(ctx["relationships"])
    ident = ctx["identity"]
    out = [
        "# Data Quality Audit",
        "",
        f"_Generated {ctx['generated_at']} by `src/profiling/generate_data_audit.py` from the live database and files. "
        "Every number below is computed, not typed. Re-run to refresh._",
        "",
        "## 1. Scope and method",
        "",
        "- **Read-only.** No raw, processed, database or warehouse data was changed; only files under `reports/` are written.",
        "- **Sources audited:** the PostgreSQL tables (full column profiling), the processed JSON files, the manifests, "
        "the Parquet exports and the DuckDB warehouse (counted), plus counts of the raw HTML/JSON collections.",
        "- **Checks:** per-column nulls/uniqueness/ranges, duplicate keys and rows, every declared foreign key, "
        f"{len(rel[rel['type'] == 'logical'])} cricket-logic relationships (including scorecard and ball-by-ball reconciliation), "
        "player/team identity, and Postgres-vs-DuckDB consistency.",
        "- **Not yet done:** the formal quality score (Stage 3). No composite score is given here on purpose.",
        "",
        "## 2. Dataset overview",
        "",
        f"- Tournaments: **{counts['tournaments']}** | matches: **{counts['matches']}** | innings: **{counts['innings']}** | "
        f"deliveries: **{counts['deliveries']:,}**",
        f"- Players: **{counts['players']:,}** ({ident['players_by_source']}) | teams: **{counts['teams']}** | "
        f"distinct venue strings: **{counts['venues_distinct_text']}**",
        f"- Total runs in innings: **{counts['total_runs_in_innings']:,}** | total wickets: **{counts['total_wickets_in_innings']:,}** (super overs excluded)",
        "",
        "### Format and year distribution",
        "",
        _md_table(cricket["format_distribution"]),
        "### Coverage by tournament",
        "",
        _md_table(
            cricket["tournament_coverage"][
                [
                    "tournament_id",
                    "matches",
                    "completed_matches",
                    "no_result_or_abandoned",
                    "matches_with_batting_scorecard",
                    "completed_with_deliveries",
                    "deliveries",
                    "scorecard_coverage_pct",
                    "ball_by_ball_coverage_pct",
                    "ball_by_ball_pct_of_completed",
                ]
            ]
        ),
        "### Match stages",
        "",
        _md_table(cricket["stage_distribution"]),
        "## 3. Findings (ranked)",
        "",
    ]
    for sev in ("High", "Medium", "Low"):
        sub = findings[findings["severity"] == sev] if len(findings) else findings
        out.append(f"### {sev} ({len(sub)})")
        out.append("")
        for r in sub.itertuples():
            out.append(f"- **[{r.area}]** {r.finding}  \n  _Evidence:_ {r.evidence}")
        out.append("")
    out += [
        "## 4. Relationship checks",
        "",
        _md_table(
            rel[rel["status"] != "ok"].reindex(
                columns=[
                    "relationship",
                    "checked_rows",
                    "violating_rows",
                    "status",
                    "detail",
                    "examples",
                ]
            )
        ),
        f"{int((rel['status'] == 'ok').sum())} of {len(rel)} checks passed. Rows marked `info` are legitimate cricket events reported for transparency, not defects.",
        "",
        "## 5. Limitations of this audit",
        "",
        "- Name-based identity matching only catches exact name matches; initial/full-name variants need Stage 4 resolution.",
        "- A 'RESULT' match with no winner may be a legitimate tie or super-over decision; it is flagged for review, not asserted as an error.",
        "- Reconciliation can only be checked where both sides exist (ball-by-ball totals exist for matches with deliveries only).",
        "- Raw HTML/JSON collections are counted, not parsed; their content is audited through the processed layer.",
        "",
        "## 6. Reproduce",
        "",
        "```powershell",
        "python scripts/run_profiling.py",
        "```",
        "",
    ]
    path.write_text("\n".join(out), encoding="utf-8")


def _html_table(df: pd.DataFrame, bar_col: str | None = None) -> str:
    if df.empty:
        return "<p><em>none</em></p>"
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            v = "" if pd.isna(v) else v
            if c == bar_col and v != "":
                cells.append(
                    f'<td><div class="bar"><span style="width:{min(float(v), 100)}%"></span></div>{v}%</td>'
                )
            else:
                cells.append(f"<td>{html.escape(str(v))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def write_profile_html(ctx: dict[str, Any], path: Path) -> None:
    c = ctx["cricket"]["entity_counts"]
    cards = "".join(
        f'<div class="card"><div class="n">{v:,}</div><div class="l">{html.escape(k.replace("_", " "))}</div></div>'
        for k, v in c.items()
        if k
        in {
            "tournaments",
            "matches",
            "innings",
            "deliveries",
            "players",
            "teams",
            "venues_distinct_text",
        }
    )
    details = []
    for prof in ctx["profiles"]:
        cols = pd.DataFrame(prof["column_profiles"])
        if cols.empty:
            continue
        cols = cols[
            [
                "column",
                "dtype",
                "kind",
                "null_count",
                "null_pct",
                "unique",
                "min",
                "max",
                "mean",
                "top_values",
            ]
        ]
        issues = (
            "".join(f"<li>{html.escape(i)}</li>" for i in prof["issues"][:25]) or "<li>none</li>"
        )
        details.append(
            f"<details><summary><b>{html.escape(prof['dataset'])}</b> — {prof['rows']:,} rows × {prof['columns_count']} cols"
            f" · missing cells {prof['missing_cells']:,} · dup keys {prof['duplicate_keys']}</summary>"
            f"<p class='meta'>{html.escape(prof['path'])} · {html.escape(prof['format'])} · key: {html.escape(prof['key'] or '—')} · "
            f"dates: {html.escape(prof['date_range'] or '—')}</p><ul>{issues}</ul>{_html_table(cols, 'null_pct')}</details>"
        )
    inv = pd.DataFrame(ctx["inventory"])[
        [
            "dataset_name",
            "file_format",
            "rows",
            "columns",
            "missing_values",
            "duplicate_records",
            "date_range",
            "memory_mb",
        ]
    ]
    rel = pd.DataFrame(ctx["relationships"])
    findings = pd.DataFrame(ctx["findings"])
    css = (
        ":root{color-scheme:light dark;--bg:#fff;--fg:#1d2330;--mut:#667;--line:#dde;--acc:#2a6fdb}"
        "@media(prefers-color-scheme:dark){:root{--bg:#14171f;--fg:#e6e9f0;--mut:#99a;--line:#2b3140;--acc:#6ea0ff}}"
        "body{font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0 auto;max-width:1200px;padding:24px 16px}"
        "h1{margin:.2em 0}h2{margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:4px}"
        ".cards{display:flex;flex-wrap:wrap;gap:12px}.card{border:1px solid var(--line);border-radius:8px;padding:10px 16px;min-width:120px}"
        ".n{font-size:22px;font-weight:600}.l{color:var(--mut);font-size:12px}"
        "table{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0;display:block;overflow-x:auto}"
        "th,td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;white-space:nowrap}th{color:var(--mut)}"
        "details{border:1px solid var(--line);border-radius:6px;margin:8px 0;padding:6px 10px}summary{cursor:pointer}"
        ".meta{color:var(--mut);font-size:12px}.bar{display:inline-block;width:60px;height:7px;background:var(--line);margin-right:6px;border-radius:3px}"
        ".bar span{display:block;height:100%;background:var(--acc);border-radius:3px}"
    )
    doc = (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Cricket Data Profile</title><style>{css}</style></head><body>"
        f"<h1>Cricket World Cup — Data Profile</h1><p class='meta'>Generated {ctx['generated_at']} from live data. Read-only audit.</p>"
        f"<div class='cards'>{cards}</div>"
        f"<h2>Findings</h2>{_html_table(findings)}"
        f"<h2>Tournament coverage</h2>{_html_table(ctx['cricket']['tournament_coverage'])}"
        f"<h2>Relationship checks</h2>{_html_table(rel)}"
        f"<h2>Dataset inventory</h2>{_html_table(inv)}"
        f"<h2>Column profiles</h2>{''.join(details)}</body></html>"
    )
    path.write_text(doc, encoding="utf-8")


def run_audit(root: Path, engine: Engine, out_dir: Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    with engine.connect() as conn:
        match_map = dict(
            conn.execute(text("select match_id, tournament_id from matches")).fetchall()
        )

    db_profiles, db_rows = _db_inventory(engine, match_map)
    file_profiles, file_rows = _file_inventory(root, match_map)
    profiles = db_profiles + file_profiles
    inventory = db_rows + file_rows

    duck = root / "data" / "warehouse" / "cricket.duckdb"
    relationships = declared_foreign_keys(engine) + logical_relationships(engine)
    if duck.exists():
        relationships += warehouse_consistency(engine, str(duck))
    ctx: dict[str, Any] = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "profiles": profiles,
        "inventory": inventory,
        "relationships": relationships,
        "identity": identity_checks(engine),
        "cricket": profile_cricket(engine),
    }
    ctx["findings"] = build_findings(ctx)

    pd.DataFrame(inventory).to_csv(out_dir / "data_inventory.csv", index=False)
    pd.DataFrame(
        [
            {
                "dataset": p["dataset"],
                "rows": p["rows"],
                **{
                    k: c[k]
                    for k in (
                        "column",
                        "dtype",
                        "kind",
                        "null_count",
                        "null_pct",
                        "unique",
                        "blank_strings",
                    )
                },
            }
            for p in profiles
            for c in p["column_profiles"]
        ]
    ).to_csv(out_dir / "missing_values_report.csv", index=False)
    pd.DataFrame(
        [
            {
                "dataset": p["dataset"],
                "rows": p["rows"],
                "key": p["key"],
                "duplicate_key_rows": p["duplicate_keys"],
                "fully_duplicated_rows": p["duplicate_rows"],
                "duplicate_rows_ignoring_keys": p["duplicate_rows_ignoring_keys"],
            }
            for p in profiles
        ]
    ).to_csv(out_dir / "duplicate_records_report.csv", index=False)
    pd.DataFrame(relationships).to_csv(out_dir / "relationship_report.csv", index=False)
    ctx["cricket"]["tournament_coverage"].to_csv(out_dir / "tournament_coverage.csv", index=False)

    with engine.connect() as conn:
        players = pd.read_sql(text("select player_id, full_name from players"), conn)
    players["name_key"] = players["full_name"].str.lower().str.strip()
    dup_ids = players[players.duplicated("name_key", keep=False)].sort_values(
        ["name_key", "player_id"]
    )
    dup_ids.to_csv(out_dir / "duplicate_player_identities.csv", index=False)

    write_profile_html(ctx, out_dir / "data_profile.html")
    write_audit_markdown(ctx, out_dir / "data_quality_audit.md")
    return ctx
