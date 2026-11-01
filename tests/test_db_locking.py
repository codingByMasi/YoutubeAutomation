"""Concurrent SQLite access must wait, not fail with 'database is locked'."""

import threading
import time

from sqlalchemy import text

from studio.db import init_db, make_engine, session_scope

INSERT_VERSION = text("INSERT INTO schema_version (version, applied_at) VALUES (1, :t)")


def test_wal_and_busy_timeout(tmp_path):
    eng = make_engine(tmp_path / "s.db")
    init_db(eng)
    with eng.connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() >= 30000


def test_writer_waits_for_other_writer(tmp_path):
    eng = make_engine(tmp_path / "s.db")
    init_db(eng)
    other = make_engine(tmp_path / "s.db")
    started = threading.Event()

    def hold():
        with other.begin() as c:
            c.execute(text("DELETE FROM assets WHERE video_id = 2"))
            started.set()
            time.sleep(0.7)

    t = threading.Thread(target=hold)
    t.start()
    started.wait(5)
    with session_scope(eng) as s:  # would raise "database is locked" without busy_timeout
        s.execute(text("DELETE FROM assets WHERE video_id = 2"))
    t.join()


def test_lock_error_gets_plain_message(root):
    from sqlalchemy.exc import OperationalError

    from studio.context import build_ctx
    from studio.errors import LOCKED_HELP
    from studio.web.service import capture

    ctx = build_ctx(root)

    def boom(c):
        c.session.execute(text("INSERT INTO ideas (seed, topic, status, channel_id, created_at, demand_score,"
                               " competition_score, outlier_score) VALUES ('a','a','idea','default',"
                               "'2026-01-01',0,0,0)"))
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    res = capture(boom, ctx)
    assert not res.ok and res.error == LOCKED_HELP
    # session is usable again (rolled back, not poisoned) and the half-done insert is gone
    assert ctx.session.execute(text("SELECT count(*) FROM ideas WHERE seed='a'")).scalar() == 0
    ctx.close()


def test_ctx_close_releases_locks(root):
    from studio.context import build_ctx

    c1 = build_ctx(root)
    c1.session.execute(INSERT_VERSION, {"t": "2026-01-01"})  # flushed, uncommitted
    c1.close()
    c2 = build_ctx(root)
    c2.session.execute(text("DELETE FROM schema_version WHERE id < 0"))
    c2.session.commit()
    c2.close()


def test_many_threads_write_without_locking(tmp_path):
    eng = make_engine(tmp_path / "s.db")
    init_db(eng)
    errors = []

    def work(i):
        e = make_engine(tmp_path / "s.db")
        try:
            for _ in range(15):
                with session_scope(e) as s:
                    s.execute(INSERT_VERSION, {"t": "2026-01-01"})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            e.dispose()

    ts = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors


def test_stale_files_cleared_only_without_holders(tmp_path, monkeypatch):
    from studio.util import dblock

    db = tmp_path / "studio.db"
    db.write_text("x")
    (tmp_path / "studio.db-journal").write_text("j")
    assert [p.name for p in dblock.stale_files(db)] == ["studio.db-journal"]
    monkeypatch.setattr(dblock, "find_holders", lambda root: [dblock.Holder(1, "python", "x")])
    assert dblock.clear_stale(db, tmp_path) == []
    monkeypatch.setattr(dblock, "find_holders", lambda root: [])
    assert len(dblock.clear_stale(db, tmp_path)) == 1 and db.exists()


def test_cli_lock_output_gets_plain_message():
    from studio.errors import LOCKED_HELP
    from studio.web.service import outcome_from_process

    res = outcome_from_process(1, "OperationalError: (sqlite3.OperationalError) database is locked")
    assert res.error == LOCKED_HELP
