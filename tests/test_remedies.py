"""Error classification and in-app remedies."""

from __future__ import annotations

import sqlite3

from studio.web import remedies as rem


def test_known_errors_get_titles_and_buttons():
    cases = {
        "sqlite3.OperationalError: database is locked": ("db_locked", rem.RELEASE_LOCK),
        "Pixabay search was rejected (HTTP 401 Unauthorized).": ("key_rejected", rem.TEST_KEYS),
        "The step was killed because the host ran out of memory.": ("out_of_memory", rem.RETRY_DRAFT),
        "ffmpeg not found. Video and audio steps need ffmpeg": ("missing_tool", rem.OPEN_SETUP),
        "Blender was not found.": ("missing_tool", rem.OPEN_SETUP),
        "Google client secret file not found": ("not_signed_in", rem.OPEN_SETUP),
        "The step failed (exit code 1).": ("step_failed", rem.RETRY_FORCE),
        "totally new problem": ("unknown", rem.RETRY),
    }
    for text, (kind, button) in cases.items():
        d = rem.diagnose(text)
        assert d.kind == kind and button in d.remedies, text


def test_no_retry_buttons_when_page_cannot_rerun():
    d = rem.diagnose("The step failed (exit code 1).", can_retry=False)
    assert rem.RETRY not in d.remedies and rem.COPY_REPORT in d.remedies
    assert rem.diagnose("totally new", can_retry=False).remedies == (rem.COPY_REPORT,)


def test_release_lock_ok_and_still_locked(tmp_path):
    db = tmp_path / "studio.db"
    sqlite3.connect(db).execute("create table t(x)").connection.close()
    assert rem.release_db_lock(db).retry is True
    holder = sqlite3.connect(db, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        res = rem.release_db_lock(db)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert not res.ok and "still locked" in res.message and not res.retry
    assert rem.release_db_lock(tmp_path / "none.db").ok


def test_report_masks_secrets():
    out = rem.report("boom PIXABAY_API_KEY=abc123", "token: xyz")
    assert "abc123" not in out and "xyz" not in out and "boom" in out
