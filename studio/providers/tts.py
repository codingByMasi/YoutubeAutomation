"""Text-to-speech behind one interface: edge (default), eleven (optional), silent (dry runs)."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path
from typing import Protocol

from studio.config import Settings
from studio.util.ffmpeg import ensure_ffmpeg, run
from studio.util.retry import with_retry

WORDS_PER_SECOND = 2.5


class TTS(Protocol):
    name: str

    def synth(self, text: str, out: Path) -> Path: ...


class EdgeTTS:
    """Free Microsoft Edge voices via the edge-tts package."""

    name = "edge"

    def __init__(self, voice: str) -> None:
        self.voice = voice

    def synth(self, text: str, out: Path) -> Path:
        import edge_tts

        def go() -> None:
            try:
                asyncio.run(edge_tts.Communicate(text, self.voice).save(str(out)))
            except Exception as exc:  # aiohttp/websocket errors: treat as network trouble
                raise ConnectionError(f"{type(exc).__name__}: {exc}") from exc
        with_retry(go, "edge-tts synthesis (needs internet access to speech.platform.bing.com)")
        return out


class ElevenLabsTTS:
    """ElevenLabs text-to-speech REST API. TTS_VOICE is the ElevenLabs voice id."""

    name = "eleven"
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"

    def __init__(self, api_key: str, voice: str, model: str = "eleven_multilingual_v2") -> None:
        self.api_key, self.voice, self.model = api_key, voice, model

    def synth(self, text: str, out: Path) -> Path:
        body = json.dumps({"text": text, "model_id": self.model}).encode()

        def go() -> bytes:
            req = urllib.request.Request(self.URL.format(voice=self.voice), data=body, method="POST", headers={
                "xi-api-key": self.api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        out.write_bytes(with_retry(go, "ElevenLabs synthesis"))
        return out


class SilentTTS:
    """Silence of the estimated speaking length. For dry runs and tests only."""

    name = "silent"

    def synth(self, text: str, out: Path) -> Path:
        ensure_ffmpeg()
        seconds = max(1.0, len(text.split()) / WORDS_PER_SECOND)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds:.2f}",
             "-c:a", "libmp3lame", "-q:a", "4", str(out)], "generating silent narration")
        return out


def get_tts(settings: Settings) -> TTS:
    if settings.tts_provider == "eleven":
        settings.require("voice (TTS_PROVIDER=eleven)", "ELEVENLABS_API_KEY")
        return ElevenLabsTTS(settings.elevenlabs_api_key, settings.tts_voice)
    if settings.tts_provider == "silent":
        return SilentTTS()
    return EdgeTTS(settings.tts_voice or "en-US-AndrewNeural")
