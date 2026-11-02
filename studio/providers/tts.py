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
    """Engines implement synth(); engines that can report word times also implement synth_timed()."""

    name: str

    def synth(self, text: str, out: Path) -> Path: ...


class EdgeTTS:
    """Free Microsoft Edge voices via the edge-tts package (word timings when the installed version provides them)."""

    name = "edge"

    def __init__(self, voice: str) -> None:
        self.voice = voice

    def synth(self, text: str, out: Path, **_: object) -> Path:
        import edge_tts

        def go() -> None:
            try:
                asyncio.run(edge_tts.Communicate(text, self.voice).save(str(out)))
            except Exception as exc:  # aiohttp/websocket errors: treat as network trouble
                raise ConnectionError(f"{type(exc).__name__}: {exc}") from exc
        with_retry(go, "edge-tts synthesis (needs internet access to speech.platform.bing.com)")
        return out

    def synth_timed(self, text: str, out: Path, prosody: dict | None = None) -> list[tuple[float, float, str]] | None:
        """Synthesize with rate/pitch/volume offsets; return [(start, end, word)] from WordBoundary events, or
        None when this edge-tts version only reports sentence boundaries (the audio is still written)."""
        import edge_tts

        from studio.story.narration import edge_args
        kw = edge_args(prosody) if prosody else {}

        async def go() -> list[tuple[float, float, str]]:
            try:
                comm = edge_tts.Communicate(text, self.voice, boundary="WordBoundary", **kw)
            except TypeError:  # older edge-tts: word boundaries are the default
                comm = edge_tts.Communicate(text, self.voice, **kw)
            words, audio = [], bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
                elif chunk["type"] == "WordBoundary":
                    s = chunk["offset"] / 1e7
                    words.append((round(s, 3), round(s + chunk["duration"] / 1e7, 3), chunk["text"]))
            out.write_bytes(bytes(audio))
            return words

        def run() -> list[tuple[float, float, str]]:
            try:
                return asyncio.run(go())
            except Exception as exc:
                raise ConnectionError(f"{type(exc).__name__}: {exc}") from exc
        words = with_retry(run, "edge-tts synthesis (needs internet access to speech.platform.bing.com)")
        return words or None


class ElevenLabsTTS:
    """ElevenLabs text-to-speech REST API. TTS_VOICE is the ElevenLabs voice id."""

    name = "eleven"
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"

    def __init__(self, api_key: str, voice: str, model: str = "eleven_multilingual_v2") -> None:
        self.api_key, self.voice, self.model = api_key, voice, model

    def synth(self, text: str, out: Path, previous_text: str = "", next_text: str = "",
              stability: float | None = None, **_: object) -> Path:
        """previous_text / next_text keep intonation continuous across calls; stability is per beat."""
        payload: dict = {"text": text, "model_id": self.model}
        if previous_text:
            payload["previous_text"] = previous_text[-400:]
        if next_text:
            payload["next_text"] = next_text[:400]
        if stability is not None:
            payload["voice_settings"] = {"stability": stability, "similarity_boost": 0.75}
        body = json.dumps(payload).encode()

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

    def synth(self, text: str, out: Path, **_: object) -> Path:
        ensure_ffmpeg()
        seconds = max(1.0, len(text.split()) / WORDS_PER_SECOND)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds:.2f}",
             "-c:a", "libmp3lame", "-q:a", "4", str(out)], "generating silent narration")
        return out


def _wav_to_mp3(wav: Path, out: Path) -> Path:
    ensure_ffmpeg()
    run(["ffmpeg", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-q:a", "4", str(out)], "converting narration")
    wav.unlink(missing_ok=True)
    return out


class KokoroTTS:
    """Kokoro (optional, runs on CPU). Used first when the `kokoro` package is installed."""

    name = "kokoro"

    def __init__(self, voice: str = "af_heart") -> None:
        self.voice = voice

    @staticmethod
    def available() -> bool:
        import importlib.util
        return importlib.util.find_spec("kokoro") is not None and importlib.util.find_spec("soundfile") is not None

    def synth(self, text: str, out: Path, prosody: dict | None = None, **_: object) -> Path:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        speed = 1.0 + (prosody or {}).get("rate", 0) / 100.0
        pipe = KPipeline(lang_code="a")
        audio = [np.asarray(a) for _, _, a in pipe(text, voice=self.voice, speed=speed)]
        wav = out.with_suffix(".wav")
        sf.write(str(wav), np.concatenate(audio), 24000)
        return _wav_to_mp3(wav, out)


class PiperTTS:
    """Piper (optional, offline). The fallback when edge-tts cannot be reached. Needs PIPER_MODEL=<voice .onnx>."""

    name = "piper"

    def __init__(self, model: str) -> None:
        self.model = model

    @staticmethod
    def available(model: str = "") -> bool:
        import shutil
        return bool(model) and Path(model).exists() and shutil.which("piper") is not None

    def synth(self, text: str, out: Path, **_: object) -> Path:
        import subprocess
        wav = out.with_suffix(".wav")
        subprocess.run(["piper", "--model", self.model, "--output_file", str(wav)], input=text.encode(),
                       check=True, capture_output=True, timeout=600)
        return _wav_to_mp3(wav, out)


class FallbackTTS:
    """Tries engines in order; each failure is logged as an issue with a fix, and the next engine is used."""

    def __init__(self, engines: list[TTS], root: Path | None = None) -> None:
        self.engines, self.root = engines, root
        self.name = "+".join(e.name for e in engines)
        self.last_used = engines[0].name

    def _try(self, method: str, *args, **kw):
        from studio import health
        steps = [(e.name, (lambda e=e: getattr(e, method)(*args, **kw))) for e in self.engines
                 if hasattr(e, method)]
        name, result = health.with_fallback(self.root, "voice", steps)
        self.last_used = name
        return result

    def synth(self, text: str, out: Path, **kw: object) -> Path:
        return self._try("synth", text, out, **kw)

    def synth_timed(self, text: str, out: Path, prosody: dict | None = None):
        timed = [e for e in self.engines if hasattr(e, "synth_timed")]
        if not timed:
            self._try("synth", text, out)
            return None
        try:
            return self._try("synth_timed", text, out, prosody)
        except Exception:  # noqa: BLE001 - timing engines failed: plain engines still produce audio
            self._try("synth", text, out, prosody=prosody)
            return None


def get_tts(settings: Settings) -> TTS:
    """The voice engine. `silent` and explicit `eleven` are respected; the default (`edge`) builds a fallback chain
    in TTS_ORDER (default kokoro,edge,piper): engines that are not installed are skipped."""
    if settings.tts_provider == "silent":
        return SilentTTS()
    chain: list[TTS] = []
    if settings.tts_provider == "eleven":
        settings.require("voice (TTS_PROVIDER=eleven)", "ELEVENLABS_API_KEY")
        chain.append(ElevenLabsTTS(settings.elevenlabs_api_key, settings.tts_voice))
    order = [x.strip() for x in (getattr(settings, "tts_order", "") or "kokoro,edge,piper").split(",") if x.strip()]
    piper_model = getattr(settings, "piper_model", "")
    for name in order:
        if name == "kokoro" and KokoroTTS.available() and settings.tts_provider != "eleven":
            chain.append(KokoroTTS())
        elif name == "edge":
            chain.append(EdgeTTS(settings.tts_voice or "en-US-AndrewNeural"))
        elif name == "piper" and PiperTTS.available(piper_model):
            chain.append(PiperTTS(piper_model))
    if len(chain) == 1:
        return chain[0]
    return FallbackTTS(chain, settings.root)
