"""Small shared helpers used across packages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if missing; return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any, *, overwrite: bool = False) -> Path:
    """Write JSON to disk. Refuses to overwrite unless explicitly allowed."""
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing file (raw data protection): {path}"
        )
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
    return path


def read_json(path: Path) -> Any:
    """Read a JSON file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def slugify(value: str) -> str:
    """Simple filesystem-safe slug."""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_").lower()
