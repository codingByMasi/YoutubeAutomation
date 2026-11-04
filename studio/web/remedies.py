"""Known error types -> a friendly diagnosis plus in-app fix actions. No Streamlit imports, so it is unit-tested.

`diagnose` reads an error message (or an Outcome) and returns a Diagnosis with a plain title and a list of Remedy
actions. `apply_remedy` runs the actions that need no UI (releasing a database lock, testing keys); the rest
(retry, open Setup, retry in draft mode) are carried out by `remedy_ui.error_panel`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# Remedy ids. The UI maps each to a button.
RELEASE_LOCK = "release_lock"
RETRY = "retry"
RETRY_FORCE = "retry_force"
RETRY_DRAFT = "retry_draft"
OPEN_SETUP = "open_setup"
TEST_KEYS = "test_keys"
RECHECK = "recheck"
COPY_REPORT = "copy_report"

LABELS = {
    RELEASE_LOCK: "🔓 Release lock and retry",
    RETRY: "🔁 Retry this step",
    RETRY_FORCE: "♻️ Reset this step and run it again",
    RETRY_DRAFT: "⚡ Retry as a quick draft (720p)",
    OPEN_SETUP: "⚙️ Open Setup",
    TEST_KEYS: "🔑 Test my keys",
    RECHECK: "✅ I fixed it, check again",
    COPY_REPORT: "📋 Show a report to send me",
}


@dataclass(frozen=True)
class Diagnosis:
    """What went wrong in plain words and which in-app actions can fix it."""

    kind: str
    title: str
    remedies: tuple[str, ...] = ()


@dataclass
class RemedyResult:
    """Outcome of an action that ran without the UI."""

    ok: bool
    message: str
    retry: bool = False  # True when the failed step should now be run again
    data: list = field(default_factory=list)


# (kind, substrings that must appear (any), title, remedies). First match wins; order matters.
_RULES: list[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = [
    ("db_locked", ("database is locked", "database table is locked"),
     "The database is busy or locked", (RELEASE_LOCK, RETRY)),
    ("out_of_memory", ("ran out of memory", "killed because the host"),
     "The computer ran out of memory", (RETRY_DRAFT, RETRY)),
    ("key_rejected", ("invalid api key", "http 401", "http 403", "unauthorized", "was rejected"),
     "A key was rejected by the service", (TEST_KEYS, OPEN_SETUP, RETRY)),
    ("missing_tool", ("ffmpeg not found", "ffprobe not found", "blender was not found", "blender_path",
                      "no such file or directory: 'ffmpeg'", "no such file or directory: 'blender'"),
     "A program the studio needs is not installed", (OPEN_SETUP, RECHECK, RETRY)),
    ("not_signed_in", ("google client secret", "token.json", "sign in", "not signed in", "oauth"),
     "Google sign-in is not set up", (OPEN_SETUP, RECHECK)),
    ("network", ("timed out", "connection", "temporary failure", "name resolution", "network", "ssl"),
     "The internet connection failed", (RETRY,)),
    ("step_failed", ("the step failed", "something unexpected went wrong", "exit code"),
     "This step failed", (RETRY, RETRY_FORCE, COPY_REPORT)),
]
_FALLBACK = Diagnosis("unknown", "Something went wrong", (RETRY, COPY_REPORT))


def diagnose(error: str, *, can_retry: bool = True) -> Diagnosis:
    """Classify an error message. `can_retry=False` drops retry buttons when the page has nothing to re-run."""
    low = (error or "").lower()
    found = _FALLBACK
    for kind, needles, title, remedies in _RULES:
        if any(n in low for n in needles):
            found = Diagnosis(kind, title, remedies)
            break
    if can_retry:
        return found
    drop = {RETRY, RETRY_FORCE, RETRY_DRAFT}
    rem = tuple(r for r in found.remedies if r not in drop)
    return Diagnosis(found.kind, found.title, rem or (COPY_REPORT,))


def release_db_lock(db_path: Path) -> RemedyResult:
    """Flush the write-ahead log and check that the database accepts a write again.

    A lock held by a step that is still running cannot be (and must not be) broken, so that is reported plainly.
    """
    if not Path(db_path).exists():
        return RemedyResult(True, "There is no database yet, nothing to release.", retry=True)
    try:
        con = sqlite3.connect(str(db_path), timeout=3)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.execute("BEGIN IMMEDIATE")
            con.execute("ROLLBACK")
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        return RemedyResult(False, "The database is still locked by something else.\n"
                            f"Why: {exc}. Another step or window is probably still running.\n"
                            "Next: wait for it to finish (or close the other window), then press the button again.")
    return RemedyResult(True, "The lock is released. Running the step again...", retry=True)


def test_keys(settings) -> RemedyResult:
    """Live-test the saved stock footage keys and say which ones fail."""
    from studio.web import setup_service

    checks = setup_service.test_footage_keys(settings)
    bad = [c for c in checks if c.level != "ok"]
    if not checks:
        return RemedyResult(False, "No Pixabay or Pexels key is saved yet. Open Setup and paste one.")
    lines = [f"{'✅' if c.level == 'ok' else '❌'} {c.area}: {c.message}" for c in checks]
    return RemedyResult(not bad, "\n".join(lines), retry=not bad)


def report(error: str, log: str = "") -> str:
    """A short plain-text report the owner can paste into a chat to get help. Secrets are masked."""
    import re

    text = f"Error:\n{error.strip()}\n\nLog (end):\n{(log or '').strip()[-1500:]}"
    return re.sub(r"(?i)((?:key|token|secret)[\w\-]*\s*[=:]\s*)\S+", r"\1***", text)


# Plain-language explanation per error kind: what it means and what happens next. Shown instead of raw text.
_PLAIN = {
    "db_locked": "Another window or step is using the studio's database at the same moment. Nothing was lost. "
                 "Pressing Fix this clears the lock and runs the step again.",
    "out_of_memory": "This computer ran out of memory while making the video. Nothing was lost. "
                     "Fix this retries it as a quick, lighter draft.",
    "key_rejected": "A service refused one of your keys, so it is wrong, expired or out of allowance. "
                    "Fix this tests your keys and shows which one needs replacing.",
    "missing_tool": "A free program the studio needs is not installed on this computer. "
                    "Fix this opens Setup, which shows how to add it.",
    "not_signed_in": "The studio is not signed in to Google yet. Fix this opens Setup so you can sign in.",
    "network": "The internet connection dropped or was too slow. Nothing was lost. Fix this tries again.",
}
_GENERIC = ("This step stopped before it finished. Your finished work is kept, so nothing needs redoing. "
            "Fix this tries the step again and, if it still fails, makes a short report you can send to Claude.")


def plain_message(error: str, kind: str) -> str:
    """The error in words a non-technical owner can act on. The raw text belongs under 'Technical details'."""
    if kind in _PLAIN:
        return _PLAIN[kind]
    why = [ln.strip() for ln in (error or "").splitlines() if ln.strip().startswith(("Why:", "Next:"))]
    return f"{_GENERIC}\n\n" + "\n".join(why) if why else _GENERIC


def save_report(root: Path, error: str, log: str = "") -> tuple[Path, str]:
    """Save a masked error report under logs/error_reports/ so the owner can copy it later. Returns (path, text)."""
    from datetime import datetime

    text = report(error, log)
    folder = Path(root) / "logs" / "error_reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"error-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    path.write_text(text, encoding="utf-8")
    return path, text


def fix_this(root: Path, error: str, log: str = "") -> RemedyResult:
    """The 'Fix this' button for errors the studio can fix with no UI: a known logged fix, else a saved report.

    `retry` on the result says the failed step should now run again. For an unknown error the report text is in `data`.
    """
    from studio import health

    hit = health.issue_for_text(root, error)
    fix = (hit or {}).get("fix") or ""
    if hit and fix.partition(":")[0] not in ("retry", "help", "youtube_signin"):
        try:
            return RemedyResult(True, health.run_fix(root, hit["id"]), retry=True)
        except Exception as exc:  # noqa: BLE001 - a failed fix must say so, not crash the page
            return RemedyResult(False, f"The automatic fix did not work: {exc}")
    _, text = save_report(root, error, log)
    return RemedyResult(False, "No automatic fix is known for this one. A report was saved in the app. "
                        "Copy it with the button on the box below and send it to Claude.", retry=True, data=[text])
