"""Character voices for skit speech lines.

Every `speech` line of a skit is spoken in its character's own voice (`cast.voice_for`; historical figures get a
stable voice picked from the roster's voices). The lines are synthesised once in `visuals` (after the scenes are
assigned), saved under `projects/<id>/speech/`, and their real length is stored in the line (`seconds`, `audio`).
The scene renderer shows each bubble and moves the speaker's mouth with that audio; `build` mixes the lines into
the narration track, with the narrator silent while a character speaks (`line_times` is shared by both).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from studio.history import cast
from studio.providers import voices
from studio.util import ffmpeg as ff
from studio.util.logging import get_logger

log = get_logger("speech_audio")
GAP = 0.35  # seconds between two spoken lines
LEAD = 0.5  # seconds before the first line
DUCK = 0.0  # narrator volume while a character speaks (silent: two voices must never overlap)


# Voices by what the script says about a character (all ids are used by the recurring cast, so they exist).
_MALE = [("bm_george", "en-GB-RyanNeural"), ("am_adam", "en-US-GuyNeural"), ("bm_lewis", "en-GB-ThomasNeural"),
         ("am_fenrir", "en-US-ChristopherNeural"), ("bm_daniel", "en-IE-ConnorNeural"), ("am_onyx", "en-US-EricNeural")]
_FEMALE = [("bf_emma", "en-GB-SoniaNeural"), ("bf_isabella", "en-GB-LibbyNeural"), ("af_heart", "en-CA-ClaraNeural")]
_YOUNG = {"male": ("am_puck", "en-AU-WilliamNeural"), "female": ("af_heart", "en-CA-ClaraNeural"),
          "neutral": ("af_heart", "en-CA-ClaraNeural")}


def voice_from_spec(spec: dict) -> dict:
    """A voice that fits a described character: gender, age and (optionally) a pitch hint (low/mid/high) or an
    explicit `voice` dict from the script. Stable for the same character name."""
    if isinstance(spec.get("voice"), dict) and spec["voice"]:
        return voices.check(spec["voice"], str(spec.get("name", "character")))
    g = str(spec.get("gender") or "neutral").lower()
    g = g if g in ("male", "female") else "neutral"
    age = str(spec.get("age") or "adult").lower()
    h = int(hashlib.sha1(str(spec.get("name", "")).lower().encode()).hexdigest(), 16)
    if age == "child":
        kok, edge = _YOUNG[g]
        speed, pitch = 1.18, 6
    else:
        pool = _MALE if g == "male" else _FEMALE if g == "female" else _MALE + _FEMALE
        kok, edge = pool[h % len(pool)]
        speed, pitch = (0.9, -4) if age == "elder" else (1.0, 0)
    hint = str(spec.get("pitch") or spec.get("voice_hint") or "").lower()
    pitch += {"low": -8, "high": 8}.get(hint, 0)
    speed += {"low": -0.04, "high": 0.04}.get(hint, 0)
    return voices.check({"edge": edge, "kokoro": kok, "speed": round(speed, 2), "pitch": pitch, "rate": 0},
                        str(spec.get("name", "character")))


def voice_for(who: str, characters: list[dict] | None = None) -> dict:
    """The voice dict for a roster id or name, a character the script describes, or (stable by name) anyone else."""
    low = (who or "").strip().lower()
    if low in cast.ROSTER:
        return cast.voice_for(low)
    for cid, c in cast.ROSTER.items():
        if low == c["name"].lower():
            return cast.voice_for(cid)
    for c in characters or []:
        if isinstance(c, dict) and str(c.get("name", "")).strip().lower() == low:
            return voice_from_spec(c)
    h = int(hashlib.sha1(low.encode()).hexdigest(), 16)
    pool = [c["voice"] for c in cast.ROSTER.values()]
    base = dict(pool[h % len(pool)])
    base["speed"] = round(min(1.3, max(0.7, float(base.get("speed", 1.0)) + ((h >> 8) % 7 - 3) * 0.02)), 2)
    return voices.check(base, who)


def line_times(speech: list[dict], dur: float) -> list[float]:
    """Start second of every speech line in a scene of `dur` seconds. Uses real audio lengths when all lines have
    them (one after another, gaps squeezed if needed), else spreads the lines evenly."""
    n = len(speech)
    if not n:
        return []
    secs = [float(s.get("seconds") or 0) for s in speech]
    if all(secs):
        room = max(0.0, dur - LEAD - 0.3 - sum(secs))
        gap = min(GAP, room / max(1, n - 1)) if n > 1 else 0.0
        starts, t = [], LEAD
        for sec in secs:
            starts.append(round(t, 3))
            t += sec + gap
        return starts
    return [round(LEAD + k * (dur - 1.2) / n, 3) for k in range(n)]


def _engines(settings, voice: dict) -> list:
    from studio.providers.tts import EdgeTTS, KokoroOnnxTTS
    out: list = []
    if KokoroOnnxTTS.available():
        out.append(KokoroOnnxTTS(voice["kokoro"], voice["speed"]))
    out.append(EdgeTTS(voice["edge"]))
    return out


def synth_lines(settings, project_dir: Path, segments: list[dict], say=print,
                characters: list[dict] | None = None) -> int:
    """Voice every speech line of every skit. Returns how many lines have audio. Never raises for a failed line:
    that line simply stays text-only (the scene then times it evenly)."""
    if getattr(settings, "tts_provider", "") == "silent":
        return 0
    folder = Path(project_dir) / "speech"
    folder.mkdir(parents=True, exist_ok=True)
    done = 0
    for i, seg in enumerate(segments, 1):
        if seg.get("scene") != "skit":
            continue
        for k, line in enumerate(seg.get("speech") or [], 1):
            text = str(line.get("text", "")).strip()
            if not text:
                continue
            voice = voice_for(str(line.get("who", "")), characters)
            key = hashlib.sha1(f"{text}|{voice['kokoro']}|{voice['edge']}|{voice['speed']}|{voice['rate']}".encode()
                               ).hexdigest()[:10]
            path = folder / f"seg_{i:03d}_{k}_{key}.mp3"
            if not path.exists() or not path.stat().st_size:
                for eng in _engines(settings, voice):
                    try:
                        eng.synth(text, path, prosody=voices.prosody(voice))
                        break
                    except Exception as exc:  # noqa: BLE001 - try the next engine, then leave the line text-only
                        log.warning("Voice %s failed for segment %d line %d: %s", getattr(eng, "name", "?"), i, k, exc)
                        path.unlink(missing_ok=True)
            if path.exists() and path.stat().st_size:
                line["audio"] = str(path)
                line["seconds"] = round(ff.probe_duration(path), 3)
                done += 1
            else:
                line.pop("audio", None)
                line.pop("seconds", None)
    if done:
        say(f"Character voices: {done} speech line(s) spoken in their own voices.")
    return done


def mix_into_narration(narration: Path, segments: list[dict], spans: list[tuple[float, float]], out: Path) -> Path:
    """Overlay the characters' lines on the narration track (narrator silenced while a line plays). Returns `out`, or
    `narration` unchanged when there is no line audio."""
    items: list[tuple[float, float, Path]] = []
    for (start, end), seg in zip(spans, segments, strict=False):
        sp = [s for s in seg.get("speech") or [] if s.get("audio") and Path(s["audio"]).exists()]
        if seg.get("scene") != "skit" or not sp or len(sp) != len(seg.get("speech") or []):
            continue
        for t0, line in zip(line_times(seg["speech"], end - start), seg["speech"], strict=True):
            items.append((start + t0, float(line["seconds"]), Path(line["audio"])))
    if not items:
        return narration
    duck = "".join(f",volume={DUCK}:enable='between(t,{a:.3f},{a + d:.3f})'" for a, d, _ in items)
    parts = [f"[0:a]anull{duck}[n]"]
    for k, (a, _, _) in enumerate(items, 1):
        parts.append(f"[{k}:a]adelay={int(a * 1000)}|{int(a * 1000)},volume=1.15[l{k}]")
    mix = "[n]" + "".join(f"[l{k}]" for k in range(1, len(items) + 1))
    parts.append(f"{mix}amix=inputs={len(items) + 1}:normalize=0:duration=first[a]")
    cmd = ["ffmpeg", "-y", "-i", str(narration)]
    for _, _, p in items:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[a]", "-ar", "48000", "-ac", "1", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log.warning("Could not mix character voices: %s", r.stderr[-300:])
        return narration
    return out
