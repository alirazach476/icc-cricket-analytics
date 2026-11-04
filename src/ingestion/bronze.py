"""Bronze layer: immutable, versioned snapshots of the as-collected data (Stage 4).

Rules
* Original values are preserved; only provenance columns (``_batch_id``, ``_ingested_at``,
  ``_source_file``) are added. Nested values are kept as JSON text.
* Each run writes a *new* batch directory. An existing batch is never opened for writing, and a
  run whose content hash equals the latest batch for that entity writes nothing (idempotent).
* ``data/bronze/_manifest.json`` is append-only: one record per written batch with row count and
  SHA-256 of the content, so any later tampering or drift is detectable.
* Sources are the collected files (processed JSON, manifests, config). The database is not read.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROVENANCE = ("_batch_id", "_ingested_at", "_source_file")


def bronze_root(root: Path) -> Path:
    return root / "data" / "bronze"


# --------------------------------------------------------------------------- generic
def _scalarize(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame([{k: _scalarize(v) for k, v in r.items()} for r in rows])
    # Mixed-type object columns cannot be stored in Parquet; keep values, store as text.
    for col in df.columns:
        if df[col].dtype == object:
            kinds = {type(v) for v in df[col].dropna()}
            if len(kinds) > 1:
                df[col] = df[col].map(lambda v: None if v is None or v != v else str(v))
    return df


def content_hash(df: pd.DataFrame) -> str:
    data = df.drop(columns=[c for c in PROVENANCE if c in df.columns])
    return hashlib.sha256(data.to_csv(index=False).encode("utf-8")).hexdigest()


def _manifest_path(root: Path) -> Path:
    return bronze_root(root) / "_manifest.json"


def read_manifest(root: Path) -> list[dict[str, Any]]:
    path = _manifest_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def latest_batch(root: Path, entity: str) -> dict[str, Any] | None:
    batches = [b for b in read_manifest(root) if b["entity"] == entity]
    return batches[-1] if batches else None


def write_batch(
    root: Path, entity: str, df: pd.DataFrame, source: str, now: datetime | None = None
) -> dict[str, Any]:
    """Write ``df`` as a new immutable batch unless identical to the latest one."""
    digest = content_hash(df)
    last = latest_batch(root, entity)
    if last and last["sha256"] == digest:
        return {**last, "status": "unchanged"}

    now = now or datetime.now(UTC)
    batch_id = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = bronze_root(root) / entity / f"batch_id={batch_id}"
    if out_dir.exists():
        raise FileExistsError(f"bronze batch already exists, refusing to overwrite: {out_dir}")
    out_dir.mkdir(parents=True)

    stamped = df.copy()
    stamped["_batch_id"] = batch_id
    stamped["_ingested_at"] = now.isoformat()
    stamped["_source_file"] = (
        stamped["_source_file"] if "_source_file" in stamped.columns else source
    )
    stamped.to_parquet(out_dir / "part-0.parquet", index=False)

    record = {
        "entity": entity,
        "batch_id": batch_id,
        "rows": int(len(df)),
        "columns": list(map(str, df.columns)),
        "sha256": digest,
        "source": source,
        "written_at": now.isoformat(),
    }
    manifest = read_manifest(root)
    manifest.append(record)
    path = _manifest_path(root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {**record, "status": "written"}


def read_bronze(root: Path, entity: str) -> pd.DataFrame:
    last = latest_batch(root, entity)
    if last is None:
        raise FileNotFoundError(
            f"no bronze batch for {entity}; run scripts/build_lakehouse.py --layer bronze"
        )
    return pd.read_parquet(
        bronze_root(root) / entity / f"batch_id={last['batch_id']}" / "part-0.parquet"
    )


def verify_bronze(root: Path) -> list[str]:
    """Re-hash every latest batch against the manifest. Returns problems (empty = intact)."""
    problems: list[str] = []
    for entity in sorted({b["entity"] for b in read_manifest(root)}):
        last = latest_batch(root, entity)
        path = bronze_root(root) / entity / f"batch_id={last['batch_id']}" / "part-0.parquet"
        if not path.exists():
            problems.append(f"{entity}: missing {path}")
            continue
        df = pd.read_parquet(path)
        if content_hash(df) != last["sha256"]:
            problems.append(f"{entity}: content hash differs from manifest")
    return problems


# --------------------------------------------------------------------------- sources
def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _match_bundle_rows(root: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        k: []
        for k in (
            "matches",
            "innings",
            "teams",
            "players",
            "awards",
            "scorecards/batting",
            "scorecards/bowling",
            "scorecards/fielding",
        )
    }
    for path in sorted((root / "data" / "processed" / "matches").glob("*.json")):
        b = _load(path)
        src = _rel(root, path)
        mid = b["match_id"]
        meta = {k: v for k, v in b.items() if not isinstance(v, (list, dict))}
        out["matches"].append(
            {
                **(b.get("match") or {}),
                **{f"bundle_{k}": v for k, v in meta.items()},
                "_source_file": src,
            }
        )
        for key, entity in (
            ("innings", "innings"),
            ("teams", "teams"),
            ("players", "players"),
            ("awards", "awards"),
            ("batting_scorecards", "scorecards/batting"),
            ("bowling_scorecards", "scorecards/bowling"),
            ("fielding_scorecards", "scorecards/fielding"),
        ):
            for row in b.get(key) or []:
                out[entity].append({"match_id": mid, **row, "_source_file": src})
    return out


def _deliveries(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "data" / "processed" / "deliveries").glob("*.json")):
        d = _load(path)
        src = _rel(root, path)
        for x in d.get("deliveries") or []:
            rows.append({**x, "delivery_source": d.get("source_name"), "_source_file": src})
    return rows


def _schedule(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "data" / "raw" / "matches").glob("*/discovered_matches.json")):
        doc = _load(path)
        src = _rel(root, path)
        for m in doc.get("matches") or []:
            rows.append(
                {**m, "schedule_collected_at": doc.get("collected_at"), "_source_file": src}
            )
    return rows


def _standings(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "data" / "processed" / "standings").glob("*.json")):
        doc = _load(path)
        for r in doc.get("rows") or []:
            rows.append(
                {**r, "collected_at": doc.get("collected_at"), "_source_file": _rel(root, path)}
            )
    return rows


def _squads(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((root / "data" / "processed" / "squads").glob("*.json")):
        doc = _load(path)
        for squad in doc.get("squads") or []:
            for p in squad.get("players") or []:
                rows.append(
                    {
                        "tournament_id": doc.get("tournament_id"),
                        "team_id": squad.get("team_id"),
                        "team_name": squad.get("team_name"),
                        "announced_at": squad.get("announced_at"),
                        **p,
                        "collected_at": doc.get("collected_at"),
                        "_source_file": _rel(root, path),
                    }
                )
    return rows


def _csv(path: Path, root: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{**r, "_source_file": _rel(root, path)} for r in csv.DictReader(handle)]


def collect_sources(root: Path) -> dict[str, pd.DataFrame]:
    """Read every bronze entity from the collected files."""
    bundles = _match_bundle_rows(root)
    frames = {name: _frame(rows) for name, rows in bundles.items()}
    frames["deliveries"] = _frame(_deliveries(root))
    frames["match_schedule"] = _frame(_schedule(root))
    frames["standings"] = _frame(_standings(root))
    frames["squads"] = _frame(_squads(root))
    frames["tournaments"] = _frame(_csv(root / "data" / "manifests" / "tournaments.csv", root))
    teams_json = root / "data" / "processed" / "teams" / "teams.json"
    if teams_json.exists():
        frames["teams_registry"] = _frame(
            [
                {**t, "_source_file": _rel(root, teams_json)}
                for t in _load(teams_json).get("teams", [])
            ]
        )
    for name, rel in (
        ("tournament_awards", "config/tournament_awards.csv"),
        ("manual_squads", "config/manual_squads.csv"),
    ):
        path = root / rel
        if path.exists():
            frames[name] = _frame(_csv(path, root))
    return frames


def build_bronze(root: Path) -> list[dict[str, Any]]:
    results = []
    for entity, df in collect_sources(root).items():
        src = (
            str(df["_source_file"].iloc[0]) if "_source_file" in df.columns and len(df) else entity
        )
        source = f"{len(df['_source_file'].unique()) if '_source_file' in df.columns else 1} source file(s), e.g. {src}"
        results.append(write_batch(root, entity, df, source))
    return results
