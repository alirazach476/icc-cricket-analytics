"""Configuration loading for CricketWorldCup Analytics.

Loads YAML settings and tournament registry. Secrets come from environment / .env.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def get_project_root() -> Path:
    """Return the repository root (directory containing config/ and src/)."""
    # src/utils/config.py -> parents[2] == project root
    return Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env_path = get_project_root() / ".env"
    load_dotenv(env_path, override=False)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in YAML file: {path}")
    return data


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    """Load config/settings.yaml merged with environment overrides."""
    _load_dotenv()
    root = get_project_root()
    settings = _read_yaml(root / "config" / "settings.yaml")

    # Environment overrides (non-secret operational knobs)
    if os.getenv("LOG_LEVEL"):
        settings.setdefault("logging", {})["level"] = os.environ["LOG_LEVEL"]
    if os.getenv("APP_ENV"):
        settings.setdefault("app", {})["environment"] = os.environ["APP_ENV"]
    if os.getenv("HTTP_REQUEST_DELAY_SECONDS"):
        settings.setdefault("collection", {})["request_delay_seconds"] = float(
            os.environ["HTTP_REQUEST_DELAY_SECONDS"]
        )
    if os.getenv("DUCKDB_PATH"):
        settings.setdefault("database", {}).setdefault("duckdb", {})["path"] = os.environ[
            "DUCKDB_PATH"
        ]
    if os.getenv("PIPELINE_DRY_RUN"):
        settings.setdefault("pipeline", {})["dry_run"] = (
            os.environ["PIPELINE_DRY_RUN"].strip().lower() in {"1", "true", "yes"}
        )

    settings["_project_root"] = str(root)
    return settings


def load_tournaments() -> list[dict[str, Any]]:
    """Load tournament registry rows as plain dicts.

    Prefer ``load_tournament_registry()`` from ``src.discovery`` when you need
    validated Pydantic models. This helper remains for lightweight callers.
    """
    from src.discovery.tournament_registry import load_tournament_registry

    registry = load_tournament_registry()
    return [t.model_dump(mode="json") for t in registry.tournaments]


def load_source_rules() -> dict[str, Any]:
    """Load source access and attribution rules."""
    root = get_project_root()
    return _read_yaml(root / "config" / "source_rules.yaml")


def get_database_url() -> str:
    """Return PostgreSQL DATABASE_URL from environment."""
    _load_dotenv()
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "cricket_worldcup")
    user = os.getenv("POSTGRES_USER", "cricket")
    password = os.getenv("POSTGRES_PASSWORD", "cricket_dev_password")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def resolve_path(relative: str | Path) -> Path:
    """Resolve a path relative to the project root."""
    path = Path(relative)
    if path.is_absolute():
        return path
    return get_project_root() / path
