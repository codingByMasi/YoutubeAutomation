"""Error types whose messages always say what failed, why, and what to do next."""

from __future__ import annotations


class StudioError(Exception):
    """A user-facing error. The CLI prints it without a traceback."""

    exit_code = 1

    def __init__(self, what: str, why: str = "", next_step: str = "") -> None:
        self.what, self.why, self.next_step = what, why, next_step
        parts = [what]
        if why:
            parts.append(f"Why: {why}")
        if next_step:
            parts.append(f"Next: {next_step}")
        super().__init__("\n".join(parts))


class ConfigError(StudioError):
    """A required setting is missing or invalid."""


class QuotaError(StudioError):
    """A YouTube API call would exceed the daily quota budget."""


class StageError(StudioError):
    """A pipeline stage was run out of order or its inputs are missing."""


class GateError(StudioError):
    """The owner did not give the typed confirmation a guarded action needs."""


class InvalidAnswer(StudioError):
    """An LLM answer failed validation. `problems` holds the individual issues, `path` the saved answer."""

    def __init__(self, what: str, why: str, next_step: str, problems: list[str], path: str = "") -> None:
        super().__init__(what, why, next_step)
        self.problems, self.path = problems, path


class PendingLLMResponse(StudioError):
    """A prompt file was written and is waiting for an answer (claude_code provider)."""

    exit_code = 3


class RequestRejected(StudioError):
    """A web service answered with a non-retryable HTTP error (for example 401 for a bad API key)."""

    def __init__(self, what: str, code: int, why: str = "", next_step: str = "") -> None:
        super().__init__(what, why, next_step)
        self.code = code


LOCKED_HELP = ("The database is busy: another copy of the app or a running step is using it.\n"
               "Why: SQLite lets one program write at a time and the wait ran out.\n"
               "Next: close other Studio windows (and any extra run_app.bat / streamlit window), "
               "wait a few seconds, then try again. Nothing was lost.")


def is_locked_error(exc: BaseException) -> bool:
    """True for SQLite 'database is locked' / 'busy' errors (also when wrapped by SQLAlchemy)."""
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg or "database is busy" in msg
