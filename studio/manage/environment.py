"""Environment preflight: is this computer ready to run every stage, and can the app fix what is not?

`run_checks` inspects Python, packages, models, programs, fonts, folders, disk, internet and Windows quirks. Each
problem carries a plain fix and, where one exists, an `action` that `apply_fix` can run from the Setup page or
`python -m studio.cli preflight --fix` (install a package, download a model, install ffmpeg, make a folder).
Nothing here edits code; fixes only install packages, download models or create folders.
"""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from studio.config import Settings
from studio.errors import StudioError
from studio.manage.doctor import FAIL, OK, WARN, Check

AREA = "Computer"
MIN_PY, MAX_PY = (3, 11), (3, 13)
MIN_FREE_GB, WARN_FREE_GB = 1.0, 5.0
WHISPER_MODEL = "small"

# (import name, pip name, why, required). Required ones block every video; optional ones only lower a feature.
PACKAGES: list[tuple[str, str, str, bool]] = [
    ("typer", "typer", "the command line", True), ("sqlalchemy", "sqlalchemy", "the database", True),
    ("dotenv", "python-dotenv", "reading .env", True), ("PIL", "Pillow", "pictures and thumbnails", True),
    ("numpy", "numpy", "pictures and audio", True), ("matplotlib", "matplotlib", "charts", True),
    ("requests", "requests", "downloads", True), ("pydantic", "pydantic", "checking AI answers", True),
    ("streamlit", "streamlit", "this app", True), ("edge_tts", "edge-tts", "the free narration voice", True),
    ("psutil", "psutil", "memory checks", True),
    ("faster_whisper", "faster-whisper", "word-accurate caption timing (otherwise timing is estimated)", False),
]


def _check(level: str, message: str, fix: str = "", action: str = "") -> Check:
    return Check(AREA, level, message, fix, action)


def set_runtime_defaults() -> None:
    """Quiet or avoid known Windows problems for this process: UTF-8 console and the Hugging Face symlink warning."""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # cp1252 consoles crash on arrows and accents
        except (AttributeError, ValueError, OSError):
            pass


def check_python() -> Check:
    v = sys.version_info[:2]
    name = f"{v[0]}.{v[1]}"
    if MIN_PY <= v <= MAX_PY:
        return _check(OK, f"Python {name}.")
    return _check(WARN if v > MAX_PY else FAIL, f"Python {name} is not supported (use 3.11 to 3.13).",
                  "Install Python 3.12 from python.org, then run setup.ps1 again; it rebuilds the private "
                  "environment with the right one.")


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:  # noqa: BLE001 - a broken install is as bad as a missing one
        return False


def check_packages() -> list[Check]:
    out = []
    for mod, pip_name, why, required in PACKAGES:
        if _importable(mod):
            continue
        level = FAIL if required else WARN
        out.append(_check(level, f"Package {pip_name} is missing or broken ({why}).",
                          f"Press Fix to install it (or run: pip install {pip_name}).", f"pip:{pip_name}"))
    if not out:
        out.append(_check(OK, "All needed Python packages are installed."))
    return out


def check_svg() -> Check:
    """Characters are SVG art. cairosvg needs a native Cairo library (often missing on Windows); resvg-py does not."""
    from studio.util import svg
    eng = svg.engine()
    if eng:
        return _check(OK, f"Character art (SVG) draws correctly via {eng}.")
    return _check(FAIL, "Nothing can draw the SVG character art, so scenes show blank placeholder faces "
                  "and channel art fails.", "Press Fix to install resvg-py (self-contained, no other install).",
                  "pip:resvg-py")


def whisper_model_cached(model: str = WHISPER_MODEL) -> bool:
    from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415
    repo = f"Systran/faster-whisper-{model}"
    return isinstance(try_to_load_from_cache(repo, "model.bin"), str)


def check_whisper() -> Check:
    if not _importable("faster_whisper"):
        return _check(WARN, "faster-whisper is not installed: captions are timed from estimates and can drift.",
                      "Press Fix to install it.", "pip:faster-whisper")
    try:
        cached = whisper_model_cached()
    except Exception:  # noqa: BLE001
        cached = False
    if cached:
        return _check(OK, f"Caption model '{WHISPER_MODEL}' is downloaded.")
    return _check(WARN, f"The caption timing model '{WHISPER_MODEL}' is not downloaded yet (about 460 MB, needs "
                  "internet once). Without it caption timing is estimated.", "Press Fix to download it.",
                  "whisper_model")


def check_ffmpeg_features() -> list[Check]:
    """ffmpeg must have the H.264 encoder and subtitle burning; the winget 'full' build has both."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return [_check(FAIL, "ffmpeg is not installed or not on PATH.", "Press Fix to install it with winget "
                       "(then restart the app), or install it from gyan.dev/ffmpeg/builds.", "ffmpeg_install")]
    out: list[Check] = []
    try:
        enc = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="replace").stdout
        flt = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return [_check(FAIL, f"ffmpeg did not run ({type(exc).__name__}).", "Reinstall ffmpeg.", "ffmpeg_install")]
    if "libx264" not in enc:
        out.append(_check(FAIL, "This ffmpeg has no H.264 encoder (libx264), so videos cannot be made.",
                          "Install the full ffmpeg build.", "ffmpeg_install"))
    if " subtitles " not in flt:
        out.append(_check(WARN, "This ffmpeg cannot burn captions into the picture (no libass).",
                          "Install the full ffmpeg build.", "ffmpeg_install"))
    return out or [_check(OK, "ffmpeg has H.264 encoding and caption burning.")]


def check_fonts(settings: Settings) -> Check:
    try:
        from PIL import ImageFont

        from studio.providers import brand
        font = ImageFont.truetype(brand.font_path(settings.assets_dir), 40)
        if font.getbbox("Hg")[3] < 20:
            raise OSError("font drew too small")
        return _check(OK, "A real TrueType font loads, so text is drawn at the right size.")
    except Exception as exc:  # noqa: BLE001
        return _check(FAIL, f"No usable TrueType font ({type(exc).__name__}). Text in scenes and thumbnails would "
                      "be tiny.", "Put a .ttf file into assets/fonts, or press Fix to reinstall matplotlib "
                      "(it bundles DejaVu).", "pip:matplotlib")


def check_folders(settings: Settings) -> list[Check]:
    out = []
    for label, path in (("projects", settings.projects_dir), ("logs", settings.root / "logs"),
                        ("assets", settings.assets_dir)):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            out.append(_check(FAIL, f"Cannot write to the {label} folder {path} ({exc.strerror or exc}).",
                              "Move the app out of a protected folder (OneDrive Documents, Program Files) or "
                              "right-click it > Properties > untick Read-only.", "mkdirs"))
    return out or [_check(OK, "The app can write its folders.")]


def check_disk(settings: Settings) -> Check:
    free = shutil.disk_usage(settings.root).free / 1e9
    if free < MIN_FREE_GB:
        return _check(FAIL, f"Only {free:.1f} GB free on this drive; a render can need several GB.",
                      "Free some space (Disk Cleanup, delete old projects on the Data page).")
    if free < WARN_FREE_GB:
        return _check(WARN, f"{free:.1f} GB free; long videos may run out of space.",
                      "Free up space before rendering a long video.")
    return _check(OK, f"{free:.0f} GB free disk space.")


def check_internet(connect: Callable = socket.create_connection) -> Check:
    try:
        connect(("speech.platform.bing.com", 443), timeout=5).close()
        return _check(OK, "Internet reachable (needed for the Edge voice, stock footage, Google upload).")
    except OSError:
        return _check(WARN, "No internet: the free Edge voice, stock footage, model download and YouTube upload "
                      "will not work. Offline features still do.", "Connect to the internet and check again.")


def check_blender(settings: Settings) -> Check:
    from studio.blender import provider
    exe, why = provider.usable(settings.blender_path)
    if exe:
        return _check(OK, f"Blender 3D ready ({exe}).")
    level = WARN if settings.renderer == "blender" else OK
    return _check(level, "Blender is not set up; 3D scenes are drawn in 2D." if level == WARN else
                  "Blender not installed (only needed for optional 3D scenes).",
                  why + " Install Blender 4.2+ from blender.org, or switch Picture style to 2D in Setup."
                  if level == WARN else "")


def check_openutau(settings: Settings) -> Check:
    from studio.kids import openutau
    if openutau.find_openutau(settings.openutau_path):
        return _check(OK, "OpenUtau found (sung melodies for kids mode).")
    return _check(OK, "OpenUtau not installed (only needed for sung kids songs; spoken narration is used).")


def check_windows() -> list[Check]:
    if os.name != "nt":
        return []
    out = []
    root = str(Path(__file__).resolve().parents[2])
    if len(root) > 90:
        out.append(_check(WARN, f"The app folder path is {len(root)} characters long; Windows can fail on very "
                          "long project paths.", "Move the app to a short folder such as C:\\YoutubeAutomation."))
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            long_ok = winreg.QueryValueEx(k, "LongPathsEnabled")[0] == 1
        if not long_ok and len(root) > 60:
            out.append(_check(WARN, "Windows long paths are off and the app folder is deep.",
                              "Move the app closer to the drive root (e.g. C:\\YoutubeAutomation)."))
    except OSError:
        pass
    return out or [_check(OK, "Windows path length is fine.")]


def run_checks(settings: Settings, *, network: bool = True) -> list[Check]:
    """Every environment check, required problems first within each group. Never raises."""
    groups: list[Callable[[], list[Check] | Check | None]] = [
        check_python, check_packages, check_svg, check_ffmpeg_features, check_whisper,
        lambda: check_fonts(settings), lambda: check_folders(settings), lambda: check_disk(settings),
        lambda: check_blender(settings), lambda: check_openutau(settings), check_windows,
    ]
    if network:
        groups.append(check_internet)
    out: list[Check] = []
    for g in groups:
        try:
            res = g()
        except Exception as exc:  # noqa: BLE001 - a check must never take the app down
            res = _check(WARN, f"A check could not run ({type(exc).__name__}: {exc}).", "")
        if isinstance(res, Check):
            out.append(res)
        elif res:
            out.extend(res)
    return out


def _pip(spec: str) -> str:
    pkgs = spec.split()
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *pkgs],
                       capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["unknown error"])[-1]
        raise StudioError(f"Installing {spec} failed.", tail,
                          "Check your internet connection (and any VPN/firewall), then press Fix again.")
    importlib.invalidate_caches()
    return f"Installed {spec}. Reload this page, then check again."


def _download_whisper() -> str:
    try:
        from faster_whisper.utils import download_model
        download_model(WHISPER_MODEL)
    except ImportError as exc:
        raise StudioError("faster-whisper is not installed.", str(exc),
                          "Press Fix on the faster-whisper line.") from exc
    except Exception as exc:  # noqa: BLE001
        raise StudioError("The caption model download failed.", f"{type(exc).__name__}: {exc}",
                          "Check your internet connection and press Fix again.") from exc
    return f"Downloaded the '{WHISPER_MODEL}' caption model."


def _install_ffmpeg() -> str:
    if not shutil.which("winget"):
        raise StudioError("Windows' winget tool was not found.", "It installs ffmpeg automatically.",
                          "Download ffmpeg from https://www.gyan.dev/ffmpeg/builds/ (release full) and add its "
                          "bin folder to PATH.")
    r = subprocess.run(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements",
                        "--accept-package-agreements"], capture_output=True, text=True, timeout=1800,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 and "already installed" not in (r.stdout + r.stderr).lower():
        raise StudioError("winget could not install ffmpeg.", (r.stdout or r.stderr).strip()[-300:],
                          "Install it by hand from https://www.gyan.dev/ffmpeg/builds/ and restart the app.")
    return "ffmpeg installed. Close the app and open it again so Windows finds it."


def _make_folders(settings: Settings) -> str:
    for p in (settings.projects_dir, settings.root / "logs", settings.assets_dir):
        p.mkdir(parents=True, exist_ok=True)
    return "Folders created."


def apply_fix(action: str, settings: Settings) -> str:
    """Run one fix action from a Check. Returns a message; raises StudioError (what / why / next) on failure."""
    kind, _, arg = action.partition(":")
    if kind == "pip":
        return _pip(arg)
    if kind == "whisper_model":
        return _download_whisper()
    if kind == "ffmpeg_install":
        return _install_ffmpeg()
    if kind == "mkdirs":
        return _make_folders(settings)
    raise StudioError(f"No automatic fix for {action!r}.", "", "Follow the instructions on the line.")


def render(checks: list[Check]) -> str:
    icon = {OK: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]"}
    lines = []
    for c in checks:
        lines.append(f"{icon[c.level]} {c.message}")
        if c.fix and c.level != OK:
            lines.append(f"         -> {c.fix}" + ("   (auto-fix: preflight --fix)" if c.action else ""))
    return "\n".join(lines)
