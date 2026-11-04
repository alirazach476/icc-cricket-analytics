"""Dataset-level profiling and the data-inventory row format."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from src.profiling.profile_columns import AUDIT_COLUMNS, hashable, profile_column

MISSING_FLAG_PCT = 50.0


def _frame_for_dupes(df: pd.DataFrame, drop: Iterable[str] = ()) -> pd.DataFrame:
    cols = [c for c in df.columns if c not in set(drop)]
    return pd.DataFrame({c: hashable(df[c]) for c in cols})


def _tournament_coverage(df: pd.DataFrame, match_to_tournament: dict[str, str] | None) -> list[str]:
    if "tournament_id" in df.columns:
        return sorted(df["tournament_id"].dropna().astype(str).unique())
    if match_to_tournament and "match_id" in df.columns:
        ids = df["match_id"].dropna().astype(str).unique()
        return sorted({match_to_tournament[i] for i in ids if i in match_to_tournament})
    return []


def profile_dataframe(
    name: str,
    df: pd.DataFrame,
    *,
    path: str | None = None,
    fmt: str = "table",
    key: str | list[str] | None = None,
    match_to_tournament: dict[str, str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Profile one tabular dataset. ``key`` is the intended unique identifier."""
    key_cols = [key] if isinstance(key, str) else list(key or [])
    key_cols = [k for k in key_cols if k in df.columns]
    columns = [profile_column(df[c]) for c in df.columns] if len(df.columns) else []

    dup_rows = int(_frame_for_dupes(df).duplicated().sum()) if len(df) else 0
    # Business duplicates: identical apart from surrogate keys and audit timestamps.
    business_drop = set(key_cols) | AUDIT_COLUMNS
    dup_business = (
        int(_frame_for_dupes(df, business_drop).duplicated().sum())
        if len(df) and len(df.columns) > len(business_drop & set(df.columns))
        else 0
    )
    dup_keys = int(_frame_for_dupes(df[key_cols]).duplicated().sum()) if key_cols and len(df) else 0
    key_nulls = int(df[key_cols].isna().any(axis=1).sum()) if key_cols else 0

    id_candidates = [
        c["column"]
        for c in columns
        if c["column"].endswith("_id")
        and c["rows"]
        and c["unique"] == c["rows"]
        and c["null_count"] == 0
    ]

    date_mins = [
        c["min"]
        for c in columns
        if c["kind"] == "datetime" and c["min"] and c["column"] not in AUDIT_COLUMNS
    ]
    date_maxs = [
        c["max"]
        for c in columns
        if c["kind"] == "datetime" and c["max"] and c["column"] not in AUDIT_COLUMNS
    ]
    date_range = f"{min(date_mins)} .. {max(date_maxs)}" if date_mins else ""

    tournaments = _tournament_coverage(df, match_to_tournament)
    fmt_cov = {
        "ODI": sum(t.startswith("ODI_") for t in tournaments),
        "T20": sum(t.startswith("T20_") for t in tournaments),
    }

    issues: list[str] = []
    if len(df) == 0:
        issues.append("empty dataset")
    for c in columns:
        if c["rows"] and c["null_count"] == c["rows"]:
            issues.append(f"{c['column']}: 100% null")
        elif c["null_pct"] >= MISSING_FLAG_PCT:
            issues.append(f"{c['column']}: {c['null_pct']:.0f}% null")
        if c["blank_strings"]:
            issues.append(f"{c['column']}: {c['blank_strings']} blank strings")
        if c["negative_values"]:
            issues.append(f"{c['column']}: {c['negative_values']} negative values")
    if dup_keys:
        issues.append(f"{dup_keys} duplicate key rows ({'+'.join(key_cols)})")
    if key_nulls:
        issues.append(f"{key_nulls} rows with null key")
    if dup_business and dup_business != dup_rows:
        issues.append(f"{dup_business} rows duplicate ignoring surrogate keys/timestamps")
    elif dup_rows:
        issues.append(f"{dup_rows} fully duplicated rows")

    return {
        "dataset": name,
        "path": path or "",
        "format": fmt,
        "rows": int(len(df)),
        "columns_count": int(len(df.columns)),
        "column_names": list(map(str, df.columns)),
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "memory_mb": round(float(df.memory_usage(deep=True).sum()) / 1e6, 3),
        "missing_cells": int(df.isna().sum().sum()),
        "columns_with_missing": int(sum(1 for c in columns if c["null_count"])),
        "duplicate_rows": dup_rows,
        "duplicate_rows_ignoring_keys": dup_business,
        "duplicate_keys": dup_keys,
        "key": "+".join(key_cols),
        "unique_identifiers": ", ".join(id_candidates),
        "date_range": date_range,
        "tournaments_covered": len(tournaments),
        "odi_tournaments": fmt_cov["ODI"],
        "t20_tournaments": fmt_cov["T20"],
        "issues": issues,
        "note": note or "",
        "column_profiles": columns,
    }


def inventory_row(profile: dict[str, Any]) -> dict[str, Any]:
    """Flatten a dataset profile into the data_inventory.csv format."""
    return {
        "dataset_name": profile["dataset"],
        "file_path": profile["path"],
        "file_format": profile["format"],
        "rows": profile["rows"],
        "columns": profile["columns_count"],
        "column_names": "; ".join(profile["column_names"]),
        "data_types": "; ".join(f"{k}:{v}" for k, v in profile["dtypes"].items()),
        "missing_values": profile["missing_cells"],
        "columns_with_missing": profile["columns_with_missing"],
        "duplicate_records": profile["duplicate_rows"],
        "duplicate_records_ignoring_keys": profile["duplicate_rows_ignoring_keys"],
        "unique_identifiers": profile["unique_identifiers"] or profile["key"],
        "date_range": profile["date_range"],
        "tournament_coverage": profile["tournaments_covered"],
        "odi_tournaments": profile["odi_tournaments"],
        "t20_tournaments": profile["t20_tournaments"],
        "memory_mb": profile["memory_mb"],
        "potential_issues": " | ".join(profile["issues"]),
        "note": profile["note"],
    }


def file_collection_row(
    name: str, path: Path, pattern: str, *, fmt: str, note: str = "", recursive: bool = True
) -> dict[str, Any]:
    """Inventory row for a directory of files that is counted, not parsed."""
    files = [p for p in (path.rglob(pattern) if recursive else path.glob(pattern)) if p.is_file()]
    size_mb = round(sum(p.stat().st_size for p in files) / 1e6, 2)
    return {
        "dataset_name": name,
        "file_path": str(path),
        "file_format": fmt,
        "rows": len(files),
        "columns": "",
        "column_names": "",
        "data_types": "",
        "missing_values": "",
        "columns_with_missing": "",
        "duplicate_records": "",
        "duplicate_records_ignoring_keys": "",
        "unique_identifiers": "",
        "date_range": "",
        "tournament_coverage": "",
        "odi_tournaments": "",
        "t20_tournaments": "",
        "memory_mb": size_mb,
        "potential_issues": "",
        "note": (note + " " if note else "") + f"rows = file count; size {size_mb} MB",
    }
