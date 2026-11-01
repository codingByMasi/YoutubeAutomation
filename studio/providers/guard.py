"""Wrap a stock provider so a rejected or failing request never crashes a build."""

from __future__ import annotations

from collections.abc import Callable

import typer

from studio.errors import RequestRejected, StudioError
from studio.util.logging import get_logger

log = get_logger("guard")
MAX_FAILURES = 3


def key_message(service: str, var: str, code: int | None) -> str:
    """Plain-language notice for a failed stock request, naming the service and the likely cause."""
    if code in (400, 401, 403):
        return (f"{service} refused the request (HTTP {code}), so it was skipped and generated visuals are used "
                f"instead. Likely cause: the key is invalid, is not a {service} key, or is saved under the wrong "
                f"name. In .env use exactly {var}=yourkey with no quotes or spaces, or fix it on the Setup page.")
    return (f"{service} could not be reached ({'HTTP ' + str(code) if code else 'network problem'}), so it was "
            "skipped and generated visuals are used instead. Check your internet connection and try again.")


class Guarded:
    """find() that returns None instead of raising; stops calling the service after a key problem."""

    def __init__(self, inner, service: str, var: str,
                 notify: Callable[[str], None] | None = None) -> None:
        self.inner, self.service, self.var = inner, service, var
        self.notify = notify or (lambda m: typer.secho(m, fg=typer.colors.YELLOW))
        self.failures = 0
        self.disabled = False

    def find(self, keywords: list[str], exclude: set | None = None):
        """Next clip or None. Never raises StudioError or network errors."""
        if self.disabled:
            return None
        try:
            return self.inner.find(keywords, exclude)
        except Exception as exc:  # noqa: BLE001 - a stock service must never stop the build
            code = exc.code if isinstance(exc, RequestRejected) else getattr(exc, "code", None)
            self.failures += 1
            if code in (400, 401, 403) or self.failures >= MAX_FAILURES:
                self.disabled = True
                self.notify(key_message(self.service, self.var, code if isinstance(code, int) else None))
            if not isinstance(exc, (StudioError, OSError)):
                log.warning("%s failed unexpectedly: %r", self.service, exc)
            return None
