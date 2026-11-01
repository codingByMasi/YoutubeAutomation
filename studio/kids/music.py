"""Original background melody generator (free, no assets). Writes a looping WAV from a seed.

The tune is a repeated A-A-B-A phrase on a major pentatonic scale over a simple I-V-vi-IV bass, synthesised with
soft sine tones. It is generated from the title, so every video gets its own tune and nothing is copied.
"""

from __future__ import annotations

import hashlib
import random
import wave
from pathlib import Path

import numpy as np

RATE = 22050
PENTATONIC = [0, 2, 4, 7, 9]  # semitones above the root (major pentatonic)
CHORD_ROOTS = [0, 7, 9, 5]  # I V vi IV, as semitone offsets
ROOT_HZ = 261.63  # middle C


def _hz(semitones: int, octave: int = 0) -> float:
    return ROOT_HZ * 2 ** ((semitones + 12 * octave) / 12)


def phrase(rng: random.Random, beats: int = 8) -> list[int]:
    """A short melody of scale steps (indices into the pentatonic scale, 0-9 over two octaves)."""
    notes, cur = [], rng.choice([0, 2, 4])
    for _ in range(beats):
        cur = min(9, max(0, cur + rng.choice([-2, -1, 0, 1, 1, 2])))
        notes.append(cur)
    notes[-1] = 0 if rng.random() < 0.5 else 2  # settle near the root
    return notes


def _tone(freq: float, seconds: float, volume: float, bright: float = 0.25) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    wave_ = np.sin(2 * np.pi * freq * t) + bright * np.sin(2 * np.pi * 2 * freq * t)
    env = np.minimum(1.0, t / 0.01) * np.exp(-3.0 * t / max(seconds, 0.05))  # quick attack, soft decay
    return volume * wave_ * env


def score(seed: str, tempo: int = 104, melody: bool = True) -> list[tuple[float, float, float, float]]:
    """(start, length, frequency, volume) tuples for one 4-phrase loop (32 beats). `melody=False` keeps only the
    bass and chords, a bed that a sung vocal can sit on."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))
    a, b = phrase(rng), phrase(rng)
    beat = 60.0 / tempo
    events = []
    for bar, ph in enumerate([a, a, b, a]):
        for k, step in enumerate(ph if melody else []):
            octave, idx = divmod(step, 5)
            start = (bar * 8 + k) * beat
            events.append((start, beat * 0.95, _hz(PENTATONIC[idx], octave), 0.30))
        for chord in range(2):  # a bass note and a soft chord every four beats
            root = CHORD_ROOTS[(bar * 2 + chord) % 4]
            start = (bar * 8 + chord * 4) * beat
            events.append((start, beat * 3.8, _hz(root, -1), 0.28))
            events.append((start, beat * 3.8, _hz(root + 4, 0), 0.10))
            events.append((start, beat * 3.8, _hz(root + 7, 0), 0.10))
    return events


def render(seed: str, out: Path, tempo: int = 104, melody: bool = True) -> Path:
    """Write the loop to `out` as a 16-bit mono WAV and return the path (`melody=False`: chords and bass only)."""
    events = score(seed, tempo, melody)
    total = max(s + length for s, length, _, _ in events)
    buf = np.zeros(int(total * RATE) + 1)
    for start, length, freq, vol in events:
        tone = _tone(freq, length, vol)
        i = int(start * RATE)
        buf[i:i + len(tone)] += tone[: len(buf) - i]
    peak = float(np.max(np.abs(buf))) or 1.0
    pcm = (buf / peak * 0.8 * 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return out
