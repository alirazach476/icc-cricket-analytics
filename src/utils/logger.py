"""Centralized logging setup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.utils.config import get_project_root, get_settings

_CONFIGURED = False


def _configure_root_logger() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    log_cfg = settings.get("logging", {})
    level_name = str(log_cfg.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = log_cfg.get(
        "format",
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    logs_dir = get_project_root() / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:  # read-only filesystem (serverless): log under the temp dir instead
        import tempfile

        logs_dir = Path(tempfile.gettempdir()) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers when re-imported
    if not root.handlers:
        formatter = logging.Formatter(fmt)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(level)
        root.addHandler(stream_handler)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with project-wide configuration applied."""
    _configure_root_logger()
    return logging.getLogger(name)
