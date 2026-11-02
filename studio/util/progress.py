"""Live progress and cancel flag for a long step, shared by the CLI child process and the web app.

The step writes `projects/<id>/progress.json`; the web app polls it. A cancel request is the file `CANCEL` in the
same folder, which the step checks while it works.
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

STALE_SECONDS = 120  # a progress file not updated for this long belongs to a step that is no longer running


def _file(folder: Path) -> Path:
    return folder / "progress.json"


def write(folder: Path, **data) -> None:
    """Replace the progress record (stage, label, done, total, eta_seconds, finished...) with `data`."""
    try:
        tmp = _file(folder).with_suffix(".tmp")
        tmp.write_text(json.dumps({**data, "updated": time.time()}), encoding="utf-8")
        tmp.replace(_file(folder))
    except OSError:
        pass  # progress is a convenience; never fail a render because of it


def read(folder: Path) -> dict | None:
    """The last progress record, or None."""
    try:
        return json.loads(_file(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def finish(folder: Path) -> None:
    """Mark the step as no longer running."""
    cur = read(folder) or {}
    write(folder, **{**{k: v for k, v in cur.items() if k != "updated"}, "finished": True})


def is_active(folder: Path, now: float | None = None) -> bool:
    """True while a step reported progress recently and has not finished."""
    rec = read(folder)
    return bool(rec and not rec.get("finished") and (now or time.time()) - rec.get("updated", 0) < STALE_SECONDS)


def request_cancel(folder: Path) -> None:
    """Ask the running step to stop its slow work (3D scenes finish in 2D instead)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "CANCEL").write_text("cancel", encoding="utf-8")


def cancelled(folder: Path) -> bool:
    """True when a cancel was requested."""
    return (folder / "CANCEL").exists()


def clear_cancel(folder: Path) -> None:
    """Forget an earlier cancel request."""
    (folder / "CANCEL").unlink(missing_ok=True)


def fmt_duration(seconds: float) -> str:
    """'45 s', '12 min' or '2 h 05 min'."""
    s = int(round(seconds))
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"{round(s / 60)} min"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


class Run:
    """Progress of one stage: `step(done, label)` writes the record the app shows (items done, percent, time left)."""

    def __init__(self, folder: Path, stage: str, total: int, noun: str = "items") -> None:
        self.folder, self.stage, self.total, self.noun = folder, stage, max(total, 1), noun
        self.started = time.monotonic()

    def step(self, done: int, label: str = "", detail: str = "", eta_seconds: float | None = None, **extra) -> None:
        """Report `done` of the items finished. The time left is worked out from the speed so far unless given."""
        if eta_seconds is None and done > 0:
            eta_seconds = (time.monotonic() - self.started) / done * max(self.total - done, 0)
        write(self.folder, stage=self.stage, label=label or f"{done} of {self.total} {self.noun}", detail=detail,
              done=done, total=self.total, noun=self.noun, eta_seconds=eta_seconds,
              elapsed_seconds=time.monotonic() - self.started, **extra)


@contextlib.contextmanager
def tracking(folder: Path, stage: str, total: int = 1, noun: str = "items"):
    """Wrap a stage: reports it as started, and as finished (also on error) so the app never shows a stale step."""
    run = Run(folder, stage, total, noun)
    run.step(0, "Starting")
    try:
        yield run
    finally:
        finish(folder)
        clear_cancel(folder)
