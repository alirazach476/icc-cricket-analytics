"""Retry helpers for transient network failures.

Uses tenacity with conservative defaults aligned to source_rules.yaml.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


def with_http_retry(
    max_attempts: int = 3,
    multiplier: float = 2.0,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator factory for retrying transient HTTP/IO errors."""

    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
