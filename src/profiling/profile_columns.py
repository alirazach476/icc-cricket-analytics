"""Column-level profiling for any pandas Series."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import numpy as np
import pandas as pd

AUDIT_COLUMNS = {"created_at", "updated_at", "collected_at", "normalized_at", "discovered_at"}
# Columns that can never legitimately be negative.
NONNEG_HINT = re.compile(
    r"(^|_)(runs|wickets|balls|overs|extras|fours|sixes|dots|wides|noballs|byes|legbyes|"
    r"maidens|matches_played|wins|losses|ties|points_count)($|_)"
)
_DATE_NAME = re.compile(r"(date|_at$|^dob$|time$)")


def hashable(series: pd.Series) -> pd.Series:
    """Return a series safe for nunique/duplicated (lists and dicts become JSON text)."""
    if series.dtype != object:
        return series
    nonnull = series.dropna()
    if nonnull.empty:
        return series
    if nonnull.map(lambda v: isinstance(v, (list, dict, set, tuple))).any():
        return series.map(
            lambda v: (
                json.dumps(v, sort_keys=True, default=str)
                if isinstance(v, (list, dict, set, tuple))
                else v
            )
        )
    return series


def _as_datetime(series: pd.Series) -> pd.Series | None:
    """Parse to datetimes if the column holds dates (typed, date objects, or ISO strings)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    nonnull = series.dropna()
    if nonnull.empty or series.dtype != object:
        return None
    first = nonnull.iloc[0]
    if isinstance(first, (dt.date, dt.datetime, pd.Timestamp)):
        return pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")
    if isinstance(first, str) and _DATE_NAME.search(str(series.name or "")):
        sample = nonnull.head(200)
        parsed = pd.to_datetime(sample, errors="coerce", utc=True, format="ISO8601")
        if parsed.notna().mean() >= 0.95:
            return pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")
    return None


def column_kind(series: pd.Series) -> str:
    if series.dropna().empty:
        return "empty"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if _as_datetime(series) is not None:
        return "datetime"
    first = series.dropna().iloc[0]
    if isinstance(first, (bool, np.bool_)):
        return "boolean"
    h = hashable(series)
    return "categorical" if h.nunique(dropna=True) <= 50 else "text"


def profile_column(series: pd.Series) -> dict[str, Any]:
    name = str(series.name)
    total = len(series)
    nulls = int(series.isna().sum())
    h = hashable(series)
    kind = column_kind(series)
    out: dict[str, Any] = {
        "column": name,
        "dtype": str(series.dtype),
        "kind": kind,
        "rows": total,
        "null_count": nulls,
        "null_pct": round(100 * nulls / total, 2) if total else 0.0,
        "unique": int(h.nunique(dropna=True)),
        "is_constant": bool(h.nunique(dropna=True) <= 1 and nulls < total),
        "blank_strings": 0,
        "negative_values": None,
        "outliers_iqr": None,
        "min": None,
        "max": None,
        "mean": None,
        "median": None,
        "std": None,
        "top_values": None,
    }
    if kind == "numeric":
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s):
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            out.update(
                min=float(s.min()),
                max=float(s.max()),
                mean=round(float(s.mean()), 4),
                median=float(s.median()),
                std=round(float(s.std()), 4) if len(s) > 1 else 0.0,
                outliers_iqr=int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
                if iqr > 0
                else 0,
            )
            if NONNEG_HINT.search(name):
                out["negative_values"] = int((s < 0).sum())
    elif kind == "datetime":
        parsed = _as_datetime(series)
        parsed = parsed.dropna() if parsed is not None else None
        if parsed is not None and len(parsed):
            out["min"] = parsed.min().strftime("%Y-%m-%d")
            out["max"] = parsed.max().strftime("%Y-%m-%d")
    elif kind in {"categorical", "text", "boolean"}:
        strs = h.dropna().astype(str)
        out["blank_strings"] = int((strs.str.strip() == "").sum())
        top = strs.value_counts().head(5)
        out["top_values"] = "; ".join(f"{k}={v}" for k, v in top.items())
    return out
