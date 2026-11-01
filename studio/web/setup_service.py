"""Setup helpers for the web app: readiness checklist, saving keys, Google sign-in, voice and renderer choice.

No Streamlit imports, so it is unit-tested. Nothing here ever logs or echoes a secret value.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from studio.blender import provider as blender
from studio.config import FOOTAGE_PROVIDERS, RENDERERS, TTS_PROVIDERS, Settings, clean_secret
from studio.context import Ctx
from studio.errors import StudioError
from studio.manage import doctor
from studio.web.service import Outcome, capture

# Only these names may be written to .env from the browser.
ENV_KEYS = ("PEXELS_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY", "CHANNEL_ID", "TTS_PROVIDER", "TTS_VOICE",
            "FOOTAGE_PROVIDER", "RENDERER", "BLENDER_PATH", "LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL")

# Free Microsoft Edge voices that read well for explainers (edge-tts names).
VOICES = {
    "en-US-AndrewNeural": "Andrew (US man, warm and clear)",
    "en-US-GuyNeural": "Guy (US man, steady news style)",
    "en-US-AriaNeural": "Aria (US woman, friendly)",
    "en-US-JennyNeural": "Jenny (US woman, calm)",
    "en-GB-RyanNeural": "Ryan (UK man)",
    "en-GB-SoniaNeural": "Sonia (UK woman)",
    "en-AU-WilliamNeural": "William (Australian man)",
    "en-IN-NeerjaNeural": "Neerja (Indian English woman)",
}

# Short guided steps per Setup control (action name from doctor.Check.action).
HOWTO = {
    "ffmpeg": ("ffmpeg turns your pictures and narration into a video.\n"
               "1. Windows: open the Start menu, type `cmd`, and run `winget install ffmpeg`. "
               "Mac: `brew install ffmpeg`.\n2. Close this app and open it again with the launcher "
               "(`run_app.bat` on Windows)."),
    "llm": "Pick **Claude Code / paste-in** (no key needed) or enter an API key for another provider below.",
    "voice": "Pick a free voice below and press **Hear a sample**. Choose *edge* for free narration.",
    "footage": ("Stock footage is optional. For real footage get a free key at https://pixabay.com/api/docs/ "
                "(sign up, the key is shown on that page) and paste it below."),
    "client_secret": ("Only needed to upload from this app. One time, about 10 minutes:\n"
                      "1. Go to https://console.cloud.google.com/ and create a project.\n"
                      "2. *APIs and services > Library*: enable **YouTube Data API v3** and "
                      "**YouTube Analytics API**.\n"
                      "3. *OAuth consent screen*: choose External, add your Google account as a **test user**.\n"
                      "4. *Credentials > Create credentials > OAuth client ID*: type **Desktop app**.\n"
                      "5. Download the JSON and upload it below."),
    "channel_id": ("In YouTube Studio open *Settings > Channel > Advanced settings* and copy the **Channel ID** "
                   "(starts with UC). Paste it below, or on the Channels page."),
    "signin": "Press **Sign in to Google**. A browser window opens on this computer; pick the channel's account.",
}


def checks(settings: Settings) -> list[doctor.Check]:
    """The doctor report, ordered so the thing to fix first comes first (fails, then warnings, then ok)."""
    order = {doctor.FAIL: 0, doctor.WARN: 1, doctor.OK: 2}
    return sorted(doctor.run_checks(settings), key=lambda c: order[c.level])


def test_footage_keys(settings: Settings, opener=None) -> list[doctor.Check]:
    """Live test of the saved Pixabay/Pexels keys for the Setup page button."""
    return doctor.test_footage_keys(settings, opener)


def blocking(settings: Settings) -> list[doctor.Check]:
    """Only the failures that stop a video from being made (upload items are not needed to make one)."""
    return [c for c in doctor.run_checks(settings)
            if c.level == doctor.FAIL and c.action not in ("client_secret", "channel_id", "signin")]


def _parse_env(text: str) -> tuple[list[str], dict[str, int]]:
    lines = text.splitlines()
    index = {}
    for n, line in enumerate(lines):
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        if m:
            index[m.group(1)] = n
    return lines, index


def save_env(root: Path, updates: dict[str, str]) -> list[str]:
    """Write allowed settings into `<root>/.env` (kept for next time) and the running process. Returns names saved."""
    if any("\n" in str(v).strip() or "\r" in str(v).strip() for k, v in updates.items() if k in ENV_KEYS):
        raise StudioError("A value contains a line break.", "Keys and names are single-line.",
                          "Paste only the value itself.")
    clean = {k: (clean_secret(str(v)) if k.endswith("_API_KEY") else str(v).strip())
             for k, v in updates.items() if k in ENV_KEYS}
    if "TTS_PROVIDER" in clean and clean["TTS_PROVIDER"] not in TTS_PROVIDERS:
        raise StudioError("Unknown voice provider.", f"Got {clean['TTS_PROVIDER']!r}.",
                          f"Choose one of: {', '.join(sorted(TTS_PROVIDERS))}.")
    if "FOOTAGE_PROVIDER" in clean and clean["FOOTAGE_PROVIDER"] not in FOOTAGE_PROVIDERS:
        raise StudioError("Unknown footage provider.", f"Got {clean['FOOTAGE_PROVIDER']!r}.",
                          f"Choose one of: {', '.join(sorted(FOOTAGE_PROVIDERS))}.")
    if "RENDERER" in clean and clean["RENDERER"] not in RENDERERS:
        raise StudioError("Unknown picture renderer.", f"Got {clean['RENDERER']!r}.", "Choose 2d or blender.")
    if any("\n" in v or "\r" in v for v in clean.values()):
        raise StudioError("A value contains a line break.", "Keys and names are single-line.",
                          "Paste only the value itself.")
    env_file = root / ".env"
    text = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    lines, index = _parse_env(text)
    for k, v in clean.items():
        if k in index:
            lines[index[k]] = f"{k}={v}"
        else:
            lines.append(f"{k}={v}")
        os.environ[k] = v
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        env_file.chmod(0o600)
    except OSError:
        pass
    return sorted(clean)


def save_client_secret(settings: Settings, data: bytes) -> Path:
    """Validate an uploaded Google OAuth client file (Desktop app) and store it where the app looks for it."""
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise StudioError("That file is not valid JSON.", str(exc),
                          "Download the OAuth client JSON from Google Cloud again and upload that.") from exc
    if not isinstance(parsed, dict) or "installed" not in parsed:
        raise StudioError("This is not a Desktop-app OAuth client.", "It has no 'installed' section.",
                          "In Google Cloud create the OAuth client with application type 'Desktop app'.")
    target = settings.client_secret
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def can_sign_in(settings: Settings) -> bool:
    """True when a Google OAuth client file exists (sign-in then opens a browser on this computer)."""
    return settings.client_secret.exists()


def signed_in(settings: Settings) -> bool:
    """True when this channel already has a saved Google sign-in."""
    return settings.token_path.exists()


def sign_in(ctx: Ctx, run_flow: Callable | None = None, services: Callable | None = None) -> Outcome:
    """Run the Google sign-in for the active channel. Opens a browser window on the machine running the app."""
    if not can_sign_in(ctx.settings):
        return Outcome(False, "", "No Google OAuth client file yet.\nWhy: sign-in needs it to identify this app.\n"
                       "Next: upload client_secret.json on the Setup page first.")
    from studio.growth import channels
    from studio.manage import multi_analytics as ma

    def go() -> None:
        r = ma.sign_in(ctx.settings, channels.active_id(ctx.settings.root), run_flow=run_flow, services=services)
        print(f"Signed in as {r['title'] or r['youtube_channel_id'] or 'your Google account'}.")

    return capture(go)


def sign_out(settings: Settings) -> bool:
    """Forget this channel's Google sign-in (deletes only its token file)."""
    if settings.token_path.exists():
        settings.token_path.unlink()
        return True
    return False


def voice_sample(settings: Settings, voice: str, out_dir: Path,
                 text: str = "Here is how this channel will sound. Every number gets a source.") -> Path:
    """Synthesize a short sample with the chosen voice (needs internet for edge-tts) and return the audio file."""
    from studio.providers.tts import get_tts

    s = replace(settings, tts_voice=voice)
    out_dir.mkdir(parents=True, exist_ok=True)
    return get_tts(s).synth(text, out_dir / "voice_sample.mp3")


def renderer_info(settings: Settings) -> dict:
    """What the 2D / 3D choice means on this computer: {blender_ok, blender_path, note}."""
    exe, why = blender.usable(settings.blender_path)
    return {"blender_ok": exe is not None, "blender_path": str(exe) if exe else "",
            "note": "Blender 3D is ready." if exe else why}


def signed_in_for(root: Path, channel_id: str) -> bool:
    """True when the named channel profile has its own saved Google sign-in."""
    return Settings(root=root, channel_key=channel_id).token_path.exists()


def section_level(all_checks: list[doctor.Check], action: str) -> str:
    """Worst doctor level among the checks tied to one Setup control (ok when none are)."""
    levels = {c.level for c in all_checks if c.action == action}
    for lvl in (doctor.FAIL, doctor.WARN):
        if lvl in levels:
            return lvl
    return doctor.OK
