"""Retry with exponential backoff for network and 5xx errors."""

from __future__ import annotations

import socket
import time
import urllib.error
from collections.abc import Callable
from typing import TypeVar

from studio.errors import StudioError
from studio.util.logging import get_logger

T = TypeVar("T")
log = get_logger("retry")
MAX_ATTEMPTS = 5
BASE_DELAY = 1.0  # seconds; tests set this to 0


def is_retryable(exc: BaseException) -> bool:
    """True for connection problems and HTTP 5xx / 429 responses."""
    if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    if isinstance(exc, urllib.error.URLError):
        return True
    status = getattr(getattr(exc, "resp", None), "status", None)  # googleapiclient HttpError
    if status is not None:
        return int(status) >= 500 or int(status) == 429
    return False


def with_retry(fn: Callable[[], T], what: str, attempts: int = MAX_ATTEMPTS, sleep=time.sleep) -> T:
    """Call fn, retrying retryable errors with delays of 1, 2, 4, 8 s. Raise StudioError at the end."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            if attempt == attempts:
                raise StudioError(
                    f"{what} failed after {attempts} attempts.",
                    f"Last error: {exc}",
                    "Check your internet connection or the service status page, then re-run the command.",
                ) from exc
            delay = BASE_DELAY * 2 ** (attempt - 1)
            log.warning("%s failed (attempt %d/%d): %s; retrying in %.0fs", what, attempt, attempts, exc, delay)
            sleep(delay)
    raise AssertionError("unreachable")
