"""Optional NVIDIA GPU video encoding (NVENC). Automatic, never required.

`nvenc_cmd` rewrites an ffmpeg command that asks for libx264 so it asks for h264_nvenc instead. `available()` checks
once per run that this ffmpeg lists the encoder AND a tiny test encode works on this computer; with no GPU (or the
owner switched it off with STUDIO_GPU=off) everything stays on the CPU and nothing is reported as an error.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache

from studio.util.logging import get_logger

log = get_logger("gpu")
OFF_VALUES = ("off", "0", "false", "no")
# x264 preset names -> NVENC p1 (fastest) .. p7 (best quality).
_PRESETS = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "faster": "p3", "fast": "p4", "medium": "p4",
            "slow": "p5", "slower": "p6", "veryslow": "p7"}
_broken = False  # set when a real NVENC encode failed, so the rest of the run stays on the CPU


def switched_off() -> bool:
    """True when the owner turned GPU encoding off (setting STUDIO_GPU=off)."""
    return os.getenv("STUDIO_GPU", "auto").strip().lower() in OFF_VALUES


@lru_cache(maxsize=1)
def probe() -> tuple[bool, str]:
    """(works, plain-language reason). Lists the encoder, then encodes 3 black frames to prove the GPU answers."""
    try:
        listed = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False, "ffmpeg could not be started."
    if "h264_nvenc" not in listed.stdout:
        return False, "This copy of ffmpeg has no NVIDIA encoder, so the CPU is used."
    try:
        test = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                               "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False, "The NVIDIA encoder test did not finish, so the CPU is used."
    if test.returncode != 0:
        if "driver" in test.stderr.lower() and "nvenc" in test.stderr.lower():
            return False, ("Your NVIDIA graphics driver is older than this ffmpeg needs, so the CPU is used. "
                           "Updating the NVIDIA driver (nvidia.com/drivers) turns GPU encoding on by itself.")
        return False, "No NVIDIA graphics card answered the encoder test, so the CPU is used."
    return True, "Your NVIDIA graphics card encodes the video."


def available() -> bool:
    """True when GPU encoding will be used right now."""
    return not _broken and not switched_off() and probe()[0]


def status() -> dict:
    """{usable, on, message} for the Setup page: `usable` = hardware works, `on` = it will actually be used."""
    ok, why = probe()
    if ok and switched_off():
        why = "Your graphics card can encode video, but GPU encoding is switched off."
    elif ok and _broken:
        why = "The graphics card failed during this run, so the CPU is being used."
    return {"usable": ok, "on": available(), "message": why}


def mark_broken() -> None:
    """Stop using NVENC for the rest of this run (a real encode failed)."""
    global _broken
    _broken = True
    log.warning("NVENC encode failed; falling back to the CPU encoder for the rest of this run.")


def reset() -> None:
    """Forget the probe result and any failure (used by tests and the Setup 'check again' button)."""
    global _broken
    _broken = False
    getattr(probe, "cache_clear", lambda: None)()


def nvenc_cmd(cmd: list[str]) -> list[str]:
    """Copy of `cmd` using h264_nvenc in place of libx264 (preset and quality flags translated). Else `cmd` itself."""
    if "libx264" not in cmd:
        return cmd
    out: list[str] = []
    skip = 0
    for i, a in enumerate(cmd):
        if skip:
            skip -= 1
        elif a == "libx264":
            out.append("h264_nvenc")
        elif a == "-preset" and i + 1 < len(cmd):
            out += ["-preset", _PRESETS.get(cmd[i + 1], "p4")]
            skip = 1
        elif a == "-crf" and i + 1 < len(cmd):
            out += ["-rc", "vbr", "-cq", cmd[i + 1], "-b:v", "0"]
            skip = 1
        elif a in ("-x264-params", "-tune") and i + 1 < len(cmd):
            skip = 1
        else:
            out.append(a)
    return out
