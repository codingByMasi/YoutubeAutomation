"""Find and stop whatever is holding the SQLite file, and clear stale journal files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SIDE_SUFFIXES = ("-journal", "-wal", "-shm")
MARKERS = ("studio.cli", "streamlit", "blender")


@dataclass
class Holder:
    """A running process that looks like another copy of the studio or one of its steps."""

    pid: int
    name: str
    cmdline: str


def find_holders(root: Path) -> list[Holder]:
    """Other processes running the studio (app, CLI step, Blender) from any copy of this project."""
    try:
        import psutil
    except ImportError:
        return []
    out: list[Holder] = []
    mine = {os.getpid(), os.getppid()}
    for p in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if p.info["pid"] in mine or not any(m in cmd.lower() for m in MARKERS):
                continue
            if "app.py" in cmd or "studio.cli" in cmd or str(root) in cmd or str(root) in str(p.info.get("cwd") or ""):
                out.append(Holder(p.info["pid"], p.info["name"] or "", cmd[:200]))
        except (psutil.Error, OSError):
            continue
    return out


def stop(pid: int) -> bool:
    """Terminate one holder (then kill it if it ignores the request). True when it is gone."""
    try:
        import psutil
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(3)
        except psutil.TimeoutExpired:
            proc.kill()
        return True
    except Exception:  # noqa: BLE001 - already gone or not allowed
        return False


def stale_files(db_path: Path) -> list[Path]:
    """Leftover -journal / -wal / -shm files next to the database."""
    return [p for p in (Path(f"{db_path}{s}") for s in SIDE_SUFFIXES) if p.exists()]


def clear_stale(db_path: Path, root: Path) -> list[Path]:
    """Delete leftover journal files, only when no other studio process is running. Never touches the .db."""
    if find_holders(root):
        return []
    gone = []
    for p in stale_files(db_path):
        try:
            p.unlink()
            gone.append(p)
        except OSError:
            pass
    return gone
