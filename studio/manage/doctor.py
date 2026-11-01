"""`doctor`: a go/no-go readiness check before the first real video. Reads files and settings only; no network."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass

from studio.config import Settings

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    """One line of the report. `level` is ok, warn (works but weaker) or fail (blocks that step)."""

    area: str
    level: str
    message: str
    fix: str = ""
    action: str = ""  # Setup-page control: ffmpeg, llm, voice, footage, client_secret, channel_id, signin


def _client_secret(settings: Settings) -> Check:
    p = settings.client_secret
    if not p.exists():
        return Check("YouTube upload", FAIL, f"No Google OAuth file at {p}.",
                     "Create a Desktop-app OAuth client in Google Cloud and save it there (README section 3).",
                     "client_secret")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Check("YouTube upload", FAIL, f"{p.name} is not valid JSON.", "Download the OAuth client JSON again.",
                     "client_secret")
    if "installed" not in data:
        return Check("YouTube upload", FAIL, f"{p.name} is not a Desktop-app client (no 'installed' section).",
                     "Create the OAuth client with application type 'Desktop app', not 'Web application'.",
                     "client_secret")
    return Check("YouTube upload", OK, "Google OAuth client file found.")


def run_checks(settings: Settings) -> list[Check]:
    """All readiness checks, in the order the owner should fix them."""
    out: list[Check] = []
    for tool in ("ffmpeg", "ffprobe"):
        out.append(Check("Video tools", OK, f"{tool} found.") if shutil.which(tool) else
                   Check("Video tools", FAIL, f"{tool} is not installed or not on PATH.",
                         "Install ffmpeg (Windows: winget install ffmpeg; Mac: brew install ffmpeg); reopen terminal.",
                         "ffmpeg"))
    if settings.llm_provider == "claude_code":
        out.append(Check("Writing", OK, "Claude Code writes scripts via prompt files (no API key needed)."))
    else:
        out.append(Check("Writing", OK if settings.llm_api_key else FAIL, f"LLM provider {settings.llm_provider}.",
                         "" if settings.llm_api_key else "Set LLM_API_KEY or use LLM_PROVIDER=claude_code.", "llm"))
    if settings.tts_provider == "silent":
        out.append(Check("Voice", FAIL, "TTS_PROVIDER=silent makes a video with no narration.",
                         "Set TTS_PROVIDER=edge (free) or eleven in .env.", "voice"))
    elif settings.tts_provider == "eleven" and not settings.elevenlabs_api_key:
        out.append(Check("Voice", FAIL, "TTS_PROVIDER=eleven but ELEVENLABS_API_KEY is empty.",
                         "Add the key or use TTS_PROVIDER=edge.", "voice"))
    else:
        out.append(Check("Voice", OK, f"Narration via {settings.tts_provider} ({settings.tts_voice}). "
                                      "Listen to the first 20 seconds before approving."))
    keyed = settings.pexels_api_key or settings.pixabay_api_key
    if settings.footage_provider == "none" or not keyed:
        out.append(Check("Visuals", WARN, "No stock footage key: the video uses generated charts and cards only.",
                         "Add a free PIXABAY_API_KEY for real footage between charts.", "footage"))
    else:
        out.append(Check("Visuals", OK, "Stock footage key set."))
    music = [f for f in (settings.assets_dir / "music").glob("*") if f.suffix.lower() in {".mp3", ".wav", ".m4a"}] \
        if (settings.assets_dir / "music").exists() else []
    out.append(Check("Music", OK, f"{len(music)} music file(s) in assets/music.") if music else
               Check("Music", OK, "No music file: the generated royalty-free bed is used."))
    out.append(_client_secret(settings))
    if not settings.channel_id:
        out.append(Check("YouTube upload", FAIL, "CHANNEL_ID is empty in .env.",
                         "Copy your channel ID from YouTube Studio > Settings > Channel > Advanced settings.",
                         "channel_id"))
    elif not settings.channel_id.startswith("UC"):
        out.append(Check("YouTube upload", WARN, "CHANNEL_ID does not start with UC.",
                         "Use the channel ID (UC...), not the @handle.", "channel_id"))
    else:
        out.append(Check("YouTube upload", OK, "CHANNEL_ID set."))
    if settings.token_path.exists():
        out.append(Check("YouTube upload", OK, "Signed in (token.json exists)."))
    else:
        out.append(Check("YouTube upload", WARN, "Not signed in to Google yet.",
                         "Press 'Sign in to Google' in the app (Setup page); a browser opens once.", "signin"))
    return out


def verdict(checks: list[Check]) -> str:
    """'GO' if nothing fails, else 'NO-GO'. Warnings never block."""
    return "NO-GO" if any(c.level == FAIL for c in checks) else "GO"


def render(checks: list[Check]) -> str:
    """Plain-text report."""
    icon = {OK: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]"}
    lines = []
    for c in checks:
        lines.append(f"{icon[c.level]} {c.area}: {c.message}")
        if c.fix and c.level != OK:
            lines.append(f"         -> {c.fix}")
    lines.append("")
    lines.append(f"Verdict: {verdict(checks)}" + ("" if verdict(checks) == "GO" else " (fix the [FAIL] lines first)"))
    lines.append("Not checked here: real Google sign-in, upload, and edge-tts need your machine and accounts.")
    return "\n".join(lines)


def run(settings: Settings) -> bool:
    """Print the report; True when GO."""
    checks = run_checks(settings)
    print(render(checks))
    return verdict(checks) == "GO"
