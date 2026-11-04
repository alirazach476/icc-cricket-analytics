# ruff: noqa: E501
"""SYNTHETIC match conditions: pitch, weather and day/night. NOT real data.

Real pitch, weather and day/night information was never collected. This module fills the gap with
**seeded random placeholders** so dashboards, schemas and pipelines can be exercised end to end.

Guarantees (tested in tests/test_synthetic.py):
* every row carries ``is_synthetic = true`` and the generator version + seed (the database also
  enforces ``is_synthetic`` with a CHECK constraint);
* values are drawn only from the match id, the month and the format, never from the match outcome,
  scores or venue results, so they cannot leak real outcomes into features;
* generation is deterministic: the same match id and seed always give the same row, and adding
  matches never changes existing rows;
* the table lives outside gold (``data/synthetic``) and is never joined into the real marts,
  statistical tests or the ML reports.

Because the values are random, any "effect" a model finds in them is noise by construction.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

GENERATOR_VERSION = "1.0"
DEFAULT_SEED = 20260101
PITCH_TYPES = ("batting_friendly", "balanced", "bowling_friendly", "spin_friendly")
PITCH_WEIGHTS = (0.30, 0.40, 0.15, 0.15)
SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
OUTPUT = SYNTHETIC_DIR / "match_conditions" / "part-0.parquet"

COLUMNS = [
    "match_id",
    "is_synthetic",
    "generator_version",
    "seed",
    "day_night",
    "start_hour_local",
    "pitch_type",
    "temperature_c",
    "humidity_pct",
    "cloud_cover_pct",
    "wind_kmh",
    "rain_probability_pct",
    "dew_expected",
]


def _rng(match_id: str, seed: int) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{match_id}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def generate_one(
    match_id: str, match_date: pd.Timestamp, fmt: str, seed: int = DEFAULT_SEED
) -> dict:
    """One synthetic row. Uses only the id, date and format (never any result)."""
    rng = _rng(match_id, seed)
    day_night = "day_night" if rng.random() < (0.6 if fmt == "T20" else 0.4) else "day"
    start = (
        int(rng.choice([18, 19, 20])) if day_night == "day_night" else int(rng.choice([9, 10, 11]))
    )
    pitch = str(rng.choice(PITCH_TYPES, p=PITCH_WEIGHTS))
    month = pd.Timestamp(match_date).month
    # Placeholder climate: a gentle month effect, no geography (venue climate is not known).
    temp = float(np.clip(rng.normal(27 + 3 * np.cos((month - 6) / 12 * 2 * np.pi), 5.5), 8, 42))
    humidity = float(np.clip(rng.normal(62 - 0.8 * (temp - 27), 15), 15, 98))
    cloud = float(np.clip(rng.normal(45, 28), 0, 100))
    wind = float(np.clip(rng.gamma(3.0, 4.0), 0, 60))
    rain = float(np.clip(rng.beta(1.2, 6) * 100, 0, 100))
    dew = bool(day_night == "day_night" and humidity > 65 and rng.random() < 0.7)
    return {
        "match_id": match_id,
        "is_synthetic": True,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "day_night": day_night,
        "start_hour_local": start,
        "pitch_type": pitch,
        "temperature_c": round(temp, 1),
        "humidity_pct": round(humidity, 0),
        "cloud_cover_pct": round(cloud, 0),
        "wind_kmh": round(wind, 1),
        "rain_probability_pct": round(rain, 0),
        "dew_expected": dew,
    }


def generate(matches: pd.DataFrame, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    rows = [
        generate_one(str(r.match_id), pd.Timestamp(r.match_date), str(r.format), seed)
        for r in matches[["match_id", "match_date", "format"]].itertuples(index=False)
    ]
    return pd.DataFrame(rows, columns=COLUMNS).astype(
        {"start_hour_local": "int64", "seed": "int64"}
    )


def build(root: Path, seed: int = DEFAULT_SEED) -> Path:
    """Generate for every gold match and write data/synthetic/match_conditions."""
    matches = pd.read_parquet(root / "data" / "gold" / "fact_matches" / "part-0.parquet")
    df = generate(matches, seed)
    out = root / "data" / "synthetic" / "match_conditions" / "part-0.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out
