"""Voices page helpers: narration voices, vetted OpenUtau voicebanks (licence + monetisation), saved choices.

No Streamlit imports, so it is unit-tested. OpenUtau runs on the CPU; no GPU is needed.
"""

from __future__ import annotations

from pathlib import Path

from studio.config import Settings
from studio.errors import StudioError
from studio.growth import channels
from studio.kids import openutau, voicebanks
from studio.web import setup_service as setup

PREVIEW_DIR = "voicebank_previews"
AUDIO_EXT = (".wav", ".mp3", ".ogg", ".flac")


def narration_voices(settings: Settings) -> list[dict]:
    """Every narration voice with `selected` set for the one in use (a custom voice already saved is kept)."""
    voices = dict(setup.VOICES)
    if settings.tts_voice not in voices:
        voices[settings.tts_voice] = settings.tts_voice
    return [{"id": k, "label": v, "selected": k == settings.tts_voice} for k, v in voices.items()]


def select_narration(root: Path, voice: str, provider: str = "edge") -> None:
    """Save the narration voice for the .env default and the active channel, so the pipeline uses it."""
    if not voice.strip():
        raise StudioError("No voice chosen.", "The voice name was empty.", "Pick a voice from the list.")
    setup.save_env(root, {"TTS_PROVIDER": provider, "TTS_VOICE": voice})
    channels.update(root, voice=voice.strip())


def openutau_status(settings: Settings) -> dict:
    """{exe, found, note}: where OpenUtau is (OPENUTAU_PATH, then C:\\Tools\\OpenUtau and the usual folders)."""
    exe = openutau.find_openutau(settings.openutau_path)
    return {"exe": exe, "found": exe is not None,
            "note": f"OpenUtau found at {exe}. It runs on the CPU; no GPU needed." if exe else
            "OpenUtau was not found. Unzip it to C:\\Tools\\OpenUtau or set OPENUTAU_PATH in .env."}


def preview_path(root: Path, key: str) -> Path | None:
    """The saved audio preview for a voicebank, if one was added."""
    d = root / PREVIEW_DIR
    for ext in AUDIO_EXT:
        p = d / f"{key}{ext}"
        if p.is_file():
            return p
    return None


def save_preview(root: Path, key: str, name: str, data: bytes) -> Path:
    """Store an audio clip exported from OpenUtau as this voicebank's preview (vetted keys only)."""
    vb = voicebanks.get(key)
    ext = Path(name).suffix.lower()
    if ext not in AUDIO_EXT or not data:
        raise StudioError("That file is not an audio clip.", f"Got {name!r}.",
                          "In OpenUtau use File > Export Audio, then upload the .wav here.")
    d = root / PREVIEW_DIR
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob(f"{vb.key}.*"):
        old.unlink()
    out = d / f"{vb.key}{ext}"
    out.write_bytes(data)
    return out


def voicebank_cards(settings: Settings) -> list[dict]:
    """One card per vetted voicebank: licence, monetisation status, warnings, install and preview state."""
    exe = openutau.find_openutau(settings.openutau_path)
    cards = []
    for vb in voicebanks.VOICEBANKS.values():
        cards.append({
            "key": vb.key, "name": vb.name, "licence": vb.licence, "credit": vb.credit, "source": vb.source,
            "download": vb.download, "checked": vb.checked, "warnings": list(vb.warnings),
            "monetisation": voicebanks.monetisation_label(vb), "ai_warning": vb.ai_warning,
            "installed": voicebanks.is_installed(vb, exe), "preview": preview_path(settings.root, vb.key),
            "selected": vb.key == settings.sing_voicebank})
    return cards


def select_voicebank(root: Path, key: str, acknowledged: bool = False) -> None:
    """Save SING_VOICEBANK. A voicebank with an AI-content ban needs the owner's explicit acknowledgement."""
    if not key:
        setup.save_env(root, {"SING_VOICEBANK": ""})
        return
    vb = voicebanks.get(key)
    if vb.ai_warning and not acknowledged:
        raise StudioError(f"{vb.name} bans AI-generated content.",
                          "This studio uses an AI model to write scripts, so monetising may break its terms.",
                          "Ask the creator, then tick the box to confirm you checked, and select again.")
    setup.save_env(root, {"SING_VOICEBANK": vb.key})


def open_in_openutau(settings: Settings) -> str:
    """Start OpenUtau so a voicebank can be auditioned and a clip exported. Returns a message for the page."""
    exe = openutau.find_openutau(settings.openutau_path)
    if exe is None:
        raise StudioError("OpenUtau was not found.",
                          "No OpenUtau.exe at OPENUTAU_PATH, C:\\Tools\\OpenUtau or the usual folders.",
                          "Unzip OpenUtau to C:\\Tools\\OpenUtau or set OPENUTAU_PATH in .env.")
    import subprocess
    try:
        subprocess.Popen([str(exe)])
    except OSError as exc:
        raise StudioError("Could not start OpenUtau.", str(exc), f"Start {exe} yourself.") from exc
    return f"Opened {exe}."
