"""All studio data lives under one directory (`STUDIO_HOME`, default: the app folder).

This module lists it, exports/imports it as a zip, and deletes parts of it. Secrets
(`.env`, `client_secret.json`, `token.json`) are never part of a zip unless asked for explicitly.
"""

from __future__ import annotations

import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from studio.errors import StudioError

DB_NAME = "studio.db"
DATA_DIRS = ("growth", "projects", "reports")
SECRET_FILES = ("token.json", "client_secret.json")
MEDIA_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".ogg"}
CACHE_PARTS = {"cache", "__pycache__", "tmp"}
MANIFEST = "manifest.json"
CONFIRM_WORD = "DELETE"


@dataclass
class Area:
    """One row in the Data page: a named part of the data and its size on disk."""

    name: str
    path: Path
    bytes: int


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def usage(root: Path) -> list[Area]:
    """Size of every top-level data area (database, growth, projects, reports, logs, cache, secrets)."""
    items = [("Database", root / DB_NAME), ("Growth plans and channels", root / "growth"),
             ("Videos (projects)", root / "projects"), ("Reports", root / "reports"), ("Logs", root / "logs"),
             ("Download cache", root / "assets" / "cache")]
    items += [(f"Secret: {n}", root / n) for n in SECRET_FILES]
    return [Area(n, p, _size(p)) for n, p in items if p.exists()]


def human(n: int) -> str:
    """Format a byte count, e.g. 1.2 MB."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def project_sizes(root: Path) -> dict[int, int]:
    """Bytes used by each video folder in projects/."""
    out: dict[int, int] = {}
    base = root / "projects"
    if base.exists():
        for d in base.iterdir():
            if d.is_dir() and d.name.isdigit():
                out[int(d.name)] = _size(d)
    return out


def _include(path: Path, include_media: bool) -> bool:
    if CACHE_PARTS & set(path.parts):
        return False
    return include_media or path.suffix.lower() not in MEDIA_SUFFIXES


def iter_files(root: Path, include_media: bool = False, include_secrets: bool = False) -> Iterator[tuple[str, Path]]:
    """(archive name, path) of every file that belongs in a snapshot. The database is handled separately."""
    for d in DATA_DIRS:
        base = root / d
        if base.exists():
            for f in sorted(base.rglob("*")):
                if f.is_file() and _include(f.relative_to(root), include_media):
                    yield f.relative_to(root).as_posix(), f
    if include_secrets:
        for n in SECRET_FILES:
            if (root / n).exists():
                yield n, root / n


def fingerprint(root: Path, include_media: bool = False) -> str:
    """Cheap change detector for autosave: names, sizes and mtimes of everything a snapshot would hold."""
    parts = []
    db = root / DB_NAME
    if db.exists():
        st = db.stat()
        parts.append(f"db:{st.st_size}:{int(st.st_mtime)}")
    for name, f in iter_files(root, include_media):
        st = f.stat()
        parts.append(f"{name}:{st.st_size}:{int(st.st_mtime)}")
    return "|".join(parts)


def _db_copy(db: Path) -> bytes:
    """Consistent copy of a possibly open SQLite database (sqlite backup API)."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "copy.db"
        src_conn, dst_conn = sqlite3.connect(db), sqlite3.connect(dst)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        return dst.read_bytes()


def export_zip(root: Path, include_media: bool = False, include_secrets: bool = False) -> bytes:
    """Zip the database and data folders. Media is left out by default (it can be rebuilt)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if (root / DB_NAME).exists():
            z.writestr(DB_NAME, _db_copy(root / DB_NAME))
        for name, f in iter_files(root, include_media, include_secrets):
            z.write(f, name)
        z.writestr(MANIFEST, json.dumps({"created": datetime.now(UTC).isoformat(timespec="seconds"),
                                         "media": include_media, "secrets": include_secrets, "version": 1}))
    return buf.getvalue()


def _allowed(name: str, allow_secrets: bool) -> bool:
    if name in (MANIFEST, DB_NAME):
        return True
    if allow_secrets and name in SECRET_FILES:
        return True
    return name.split("/", 1)[0] in DATA_DIRS and "/" in name


def import_zip(root: Path, data: bytes, replace: bool = False, allow_secrets: bool = False) -> int:
    """Restore a zip made by `export_zip`. Returns the number of files written.

    Merge mode (default) overwrites files that exist in the zip and keeps everything else. Replace mode
    first clears the data areas. The old database is kept as studio.db.bak. Unsafe paths are refused.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise StudioError("That file is not a valid backup zip.", str(exc),
                          "Choose a zip made by the Data page (Export) and try again.") from exc
    names = [i.filename for i in z.infolist() if not i.is_dir()]
    for n in names:
        parts = Path(n).parts
        if n.startswith(("/", "\\")) or ".." in parts or ":" in n:
            raise StudioError(f"Unsafe path in backup: {n}", "Zip entries must stay inside the data folder.",
                              "Do not import this file.")
    if MANIFEST not in names and DB_NAME not in names:
        raise StudioError("This zip does not look like a studio backup.", "No manifest.json or studio.db inside.",
                          "Export a backup from the Data page and import that.")
    if replace:
        wipe(root, CONFIRM_WORD, keep_secrets=True)
    written = 0
    for n in names:
        if not _allowed(n, allow_secrets):
            continue
        dest = root / n
        if n == DB_NAME and dest.exists():
            shutil.copy2(dest, root / (DB_NAME + ".bak"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(n))
        written += 1
    return written


def _need_confirm(confirm: str) -> None:
    if confirm != CONFIRM_WORD:
        raise StudioError("Delete was not confirmed.", f"Confirmation must be exactly {CONFIRM_WORD}.",
                          f"Type {CONFIRM_WORD} to confirm, or cancel.")


def wipe(root: Path, confirm: str, keep_secrets: bool = True) -> None:
    """Delete ALL studio data (database, growth, projects, reports, logs, cache). Needs confirm == DELETE."""
    _need_confirm(confirm)
    for d in (*DATA_DIRS, "logs"):
        shutil.rmtree(root / d, ignore_errors=True)
    shutil.rmtree(root / "assets" / "cache", ignore_errors=True)
    for n in (DB_NAME, DB_NAME + ".bak", DB_NAME + "-wal", DB_NAME + "-shm", ".sync_state.json"):
        (root / n).unlink(missing_ok=True)
    if not keep_secrets:
        for n in SECRET_FILES:
            (root / n).unlink(missing_ok=True)


def clear_cache(root: Path) -> int:
    """Delete downloaded stock footage/photos (safe: re-downloaded when needed). Returns bytes freed."""
    c = root / "assets" / "cache"
    n = _size(c)
    shutil.rmtree(c, ignore_errors=True)
    return n


def delete_media(root: Path, video_id: int | None = None) -> int:
    """Delete rendered video/audio files (keeps scripts and data) for one video or all. Returns bytes freed."""
    base = root / "projects" / str(video_id) if video_id is not None else root / "projects"
    freed = 0
    if base.exists():
        for f in base.rglob("*"):
            if f.is_file() and f.suffix.lower() in MEDIA_SUFFIXES:
                freed += f.stat().st_size
                f.unlink()
    return freed


def delete_video(session: Session, root: Path, video_id: int, confirm: str) -> None:
    """Delete one video: its folder and database rows (titles, scripts, segments, assets, metrics, tests, drafts).

    The idea it came from is deleted too when no other video uses it. Needs confirm == DELETE.
    """
    from studio.models import ABTest, Asset, CommentDraft, Idea, MetricDaily, Script, Segment, Title, Video

    _need_confirm(confirm)
    video = session.get(Video, video_id)
    if video is not None:
        for model in (Title, Script, Segment, Asset, ABTest, CommentDraft):
            session.query(model).filter(model.video_id == video_id).delete()
        if video.youtube_video_id:
            session.query(MetricDaily).filter(MetricDaily.youtube_video_id == video.youtube_video_id).delete()
        idea_id = video.idea_id
        session.delete(video)
        session.flush()
        if not session.query(Video).filter(Video.idea_id == idea_id).count():
            session.query(Idea).filter(Idea.id == idea_id).delete()
        session.commit()
    shutil.rmtree(root / "projects" / str(video_id), ignore_errors=True)


def delete_channel_data(session: Session, root: Path, channel_id: str, confirm: str) -> list[int]:
    """Delete every idea and video of one channel plus its growth files. The channel profile itself stays.

    Returns the deleted video ids. Needs confirm == DELETE.
    """
    from studio.models import Idea, Video

    _need_confirm(confirm)
    idea_ids = [i for (i,) in session.query(Idea.id).filter(Idea.channel_id == channel_id)]
    vids = [v for (v,) in session.query(Video.id).filter(Video.idea_id.in_(idea_ids))] if idea_ids else []
    for v in vids:
        delete_video(session, root, v, confirm)
    if idea_ids:
        session.query(Idea).filter(Idea.id.in_(idea_ids)).delete(synchronize_session=False)
        session.commit()
    if channel_id != "default":
        shutil.rmtree(root / "growth" / "c" / channel_id, ignore_errors=True)
    else:
        for f in (root / "growth").glob("*.json") if (root / "growth").exists() else []:
            if f.name != "channels.json":
                f.unlink()
    return vids
