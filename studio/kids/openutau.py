"""Find OpenUtau (optional, PC only), open a project in it, and pick up the vocal WAV you export from it.

OpenUtau has no documented command-line renderer, so the step is: we write song.ustx, you press Export in the
app, and the build mixes the WAV. If no WAV exists the build keeps the normal narration and background tune.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from studio.errors import StudioError

VOCAL = "vocal.wav"


def find_openutau(configured: str = "") -> Path | None:
    """OPENUTAU_PATH setting, then PATH, then the usual Windows folders (portable unzip or installer)."""
    if configured:
        p = Path(configured)
        return p if p.is_file() else None
    found = shutil.which("OpenUtau") or shutil.which("OpenUtau.exe")
    if found:
        return Path(found)
    roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES", ""), str(Path.home()),
             str(Path.home() / "Downloads")]
    for root in filter(None, roots):
        for pattern in ("OpenUtau/OpenUtau.exe", "OpenUtau*/OpenUtau.exe", "Programs/OpenUtau/OpenUtau.exe"):
            hits = sorted(Path(root).glob(pattern))
            if hits:
                return hits[-1]
    return None


def open_project(exe: Path, ustx: Path) -> None:
    """Launch OpenUtau with the project (does not wait). Not verified against every OpenUtau version."""
    try:
        subprocess.Popen([str(exe), str(ustx)])
    except OSError as exc:
        raise StudioError("Could not start OpenUtau.", str(exc),
                          f"Open {ustx} yourself: File > Open in OpenUtau.") from exc


def vocal_path(sing_dir: Path) -> Path | None:
    """The exported vocal: sung/vocal.wav, or the newest .wav in OpenUtau's Export folder next to song.ustx."""
    direct = sing_dir / VOCAL
    if direct.is_file():
        return direct
    exports = sorted((sing_dir / "Export").glob("*.wav"), key=lambda p: p.stat().st_mtime) \
        if (sing_dir / "Export").is_dir() else []
    return exports[-1] if exports else None


def import_vocal(sing_dir: Path, wav: Path | None = None) -> Path:
    """Copy `wav` (or the newest export) to sung/vocal.wav and return it."""
    src = wav or vocal_path(sing_dir)
    if src is None or not src.is_file():
        raise StudioError("No sung vocal found.", f"Nothing at {wav or sing_dir / VOCAL} or in {sing_dir / 'Export'}.",
                          "In OpenUtau choose File > Export Audio > Mixdown To Wav File, then run this again.")
    dest = sing_dir / VOCAL
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    return dest
