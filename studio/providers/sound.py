"""Royalty-free sound made by the studio itself: a looping music bed and a few sound effects.

Nothing is downloaded, so there is no licence risk: the files are synthesized with numpy and recorded as
"own work". A track dropped into `assets/music/` always wins over the generated bed.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
OWN_LICENCE = "Own work (synthesized by studio)"

# chord progressions as lists of MIDI notes (root first). Minor = serious/analytical, major = upbeat.
PROGRESSIONS = {
    "minor": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]],   # Am F C G
    "major": [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]],   # C G Am F
}


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _write(path: Path, data: np.ndarray) -> Path:
    """Write a mono float array in -1..1 as a 16-bit stereo WAV."""
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())
    return path


def _env(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = min(n, int(attack * SR)), min(n, int(release * SR))
    if a:
        e[:a] = np.linspace(0, 1, a) ** 2
    if r:
        e[-r:] *= np.linspace(1, 0, r) ** 2
    return e


def music_bed(path: Path, mood: str = "minor", bpm: int = 88) -> Path:
    """A seamless 4-chord loop: soft pad, bass, light plucked arpeggio and a quiet pulse (about 11 s)."""
    chords = PROGRESSIONS.get(mood, PROGRESSIONS["minor"])
    beat = 60.0 / bpm
    bar = int(4 * beat * SR)
    tail = int(1.2 * SR)
    total = bar * len(chords)
    buf = np.zeros(total + tail)
    rng = np.random.default_rng(7)
    for c, notes in enumerate(chords):
        s0 = c * bar
        t = np.arange(bar + tail) / SR
        pad = np.zeros_like(t)
        for m in notes:
            for detune in (-0.12, 0.12):  # two slightly detuned voices make a warm, moving pad
                f = _hz(m + detune)
                pad += np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
        pad *= _env(bar + tail, 0.9, 1.1) * 0.05
        bass = np.sin(2 * np.pi * _hz(notes[0] - 12) * t) * _env(bar + tail, 0.05, 0.8) * 0.16
        buf[s0:s0 + bar + tail] += pad + bass
        # plucked arpeggio, one note per half beat
        step = int(beat / 2 * SR)
        for k in range(8):
            f = _hz(notes[k % 3] + 12 * (k // 3 % 2))
            n = int(0.45 * SR)
            tt = np.arange(n) / SR
            pluck = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 7) * 0.05
            at = s0 + k * step
            buf[at:at + n] += pluck[: len(buf) - at]
        # quiet hi-hat pulse on the off-beats
        for k in range(4):
            n = int(0.05 * SR)
            hat = rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 90) * 0.012
            at = s0 + int((k + 0.5) * beat * SR)
            buf[at:at + n] += hat
    buf[:tail] += buf[total:]  # wrap the tail over the start so the loop has no click
    loop = buf[:total]
    loop /= max(1e-6, np.abs(loop).max()) * 1.6
    return _write(path, loop)


def sfx_whoosh(path: Path) -> Path:
    """0.6 s filtered-noise sweep that peaks at 0.45 s: place it just before a cut."""
    n = int(0.6 * SR)
    noise = np.random.default_rng(1).standard_normal(n)
    out, y = np.zeros(n), 0.0
    for i in range(n):  # one-pole low-pass whose cutoff opens as the sweep rises
        a = 0.02 + 0.5 * (i / n) ** 2
        y += a * (noise[i] - y)
        out[i] = y
    env = np.sin(np.linspace(0, np.pi, n)) ** 3
    env = np.concatenate([env[: int(0.45 * n)], np.linspace(env[int(0.45 * n)], 0, n - int(0.45 * n))])
    out = out * env
    return _write(path, out / max(1e-6, np.abs(out).max()) * 0.6)


def sfx_pop(path: Path) -> Path:
    """Short rising blip for a chart step appearing."""
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    f = 700 + 900 * t / 0.12
    return _write(path, np.sin(2 * np.pi * f * t) * np.exp(-t * 28) * 0.45)


def sfx_hit(path: Path) -> Path:
    """Low impact with a noise burst, for reveals and big numbers."""
    n = int(0.7 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (45 + 90 * np.exp(-t * 14)) * t) * np.exp(-t * 6)
    burst = np.random.default_rng(3).standard_normal(n) * np.exp(-t * 30) * 0.25
    return _write(path, (body + burst) * 0.7)


SFX = {"whoosh": sfx_whoosh, "pop": sfx_pop, "hit": sfx_hit}


def ensure_sound(cache: Path, mood: str = "minor") -> dict[str, Path]:
    """Generate (once) the music bed and sound effects under `cache`; returns name -> wav path."""
    out = {}
    bed = cache / f"bed_{mood}.wav"
    out["music"] = bed if bed.exists() else music_bed(bed, mood)
    for name, fn in SFX.items():
        f = cache / f"sfx_{name}.wav"
        out[name] = f if f.exists() else fn(f)
    return out
