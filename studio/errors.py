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


class PendingLLMResponse(StudioError):
    """A prompt file was written and is waiting for an answer (claude_code provider)."""

    exit_code = 3
