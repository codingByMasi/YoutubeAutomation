"""Database engine, session factory and schema initialisation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from studio.errors import StudioError
from studio.models import SCHEMA_VERSION, Base, SchemaVersion


def make_engine(db_path: Path | str) -> Engine:
    """SQLite engine for a file path, or ':memory:'."""
    url = "sqlite://" if str(db_path) == ":memory:" else f"sqlite:///{db_path}"
    engine = create_engine(url, future=True, connect_args={"timeout": BUSY_TIMEOUT_MS / 1000})
    if url != "sqlite://":
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


BUSY_TIMEOUT_MS = 30_000


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    """WAL lets readers and one writer coexist; busy_timeout makes writers wait instead of failing."""
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    finally:
        cur.close()


def init_db(engine: Engine) -> None:
    """Create missing tables and record the schema version. Never drops anything."""
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    with Session(engine) as s:
        row = s.query(SchemaVersion).order_by(SchemaVersion.id.desc()).first()
        if row is None:
            s.add(SchemaVersion(version=SCHEMA_VERSION))
            s.commit()
        elif row.version > SCHEMA_VERSION:
            raise StudioError(
                f"Database schema version {row.version} is newer than this code ({SCHEMA_VERSION}).",
                "The database was created by a newer version of the studio.",
                "Update the code (git pull) before running commands.",
            )
    missing = set(Base.metadata.tables) - set(inspect(engine).get_table_names())
    if missing:
        raise StudioError(f"Tables missing after init: {sorted(missing)}", "", "Check file permissions on studio.db.")


def _add_missing_columns(engine: Engine) -> None:
    """Upgrade older databases in place: ideas.channel_id (existing rows join the "default" channel)."""
    cols = {c["name"] for c in inspect(engine).get_columns("ideas")}
    if "channel_id" not in cols:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE ideas ADD COLUMN channel_id VARCHAR(64) NOT NULL DEFAULT 'default'")


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Session that commits on success and rolls back on error."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = factory()
    try:
        yield s
        s.commit()
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()
