"""Per-character voice settings shared by the kids roster and the history cast.

A character's `voice` is a small dict:
  edge    edge-tts voice name, e.g. "en-US-AnaNeural" (list them with `edge-tts --list-voices`)
  rate    edge-tts speaking-rate offset in percent (int, -50..50)
  pitch   edge-tts pitch offset in Hz (int, -50..50)
  kokoro  Kokoro voice id, e.g. "af_sky" (offline voice; prefix a/b = US/UK, f/m = female/male)
  speed   Kokoro speed multiplier (0.7..1.3)
"""

from __future__ import annotations

import re

from studio.errors import StudioError

_EDGE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")
_KOKORO = re.compile(r"^[ab][fm]_[a-z]+$")
DEFAULT = {"edge": "en-US-AndrewNeural", "rate": 0, "pitch": 0, "kokoro": "bm_george", "speed": 1.0}


def check(voice: object, source: str = "character") -> dict:
    """Return a cleaned voice dict (missing keys filled from DEFAULT) or raise a StudioError that says what to fix."""
    if not isinstance(voice, dict):
        raise StudioError(f"{source}: voice must be an object.", "It looks like {\"edge\": \"en-US-AnaNeural\", ...}.",
                          "Fix the voice field.")
    out = {**DEFAULT, **voice}
    if not _EDGE.match(str(out["edge"])):
        raise StudioError(f"{source}: edge voice '{out['edge']}' is not a voice name.",
                          "Names look like en-US-AnaNeural.", "Run `edge-tts --list-voices` and copy a name.")
    if not _KOKORO.match(str(out["kokoro"])):
        raise StudioError(f"{source}: kokoro voice '{out['kokoro']}' is not a voice id.",
                          "Ids look like af_sky or bm_george.", "Use a Kokoro voice id.")
    for key, lo, hi in (("rate", -50, 50), ("pitch", -50, 50), ("speed", 0.7, 1.3)):
        try:
            ok = lo <= float(out[key]) <= hi
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise StudioError(f"{source}: voice {key} '{out[key]}' is out of range.", f"Use {lo} to {hi}.",
                              f"Fix voice.{key}.")
    out["rate"], out["pitch"], out["speed"] = int(out["rate"]), int(out["pitch"]), float(out["speed"])
    return out


def prosody(voice: dict) -> dict:
    """The `prosody` dict the TTS engines take (rate %, pitch Hz, volume %) for this voice."""
    return {"rate": int(voice["rate"]), "pitch": int(voice["pitch"]), "volume": 0}


def engines(voice: dict) -> dict:
    """Ready-to-use engines for a character's voice: {"edge": EdgeTTS, "kokoro": KokoroOnnxTTS}.

    Call `.synth(text, out, prosody=prosody(voice))` (or `synth_timed` on the edge engine). Nothing is synthesised
    or downloaded here; the engines only hold the voice name.
    """
    from studio.providers.tts import EdgeTTS, KokoroOnnxTTS
    return {"edge": EdgeTTS(voice["edge"]), "kokoro": KokoroOnnxTTS(voice["kokoro"], voice["speed"])}
