"""Host-character scenes: the channel mascot acts out a script beat in a small 3D set.

Pure Python (no Blender): validation, choosing an action/set/props from the narration, and a loudness envelope of the
narration audio so the mouth moves with the voice. The Blender side lives in `studio/blender/scene_script.py`.
"""

from __future__ import annotations

import array
import re
import subprocess

ACTIONS = ("present", "point", "celebrate", "shock", "think", "shrug", "walk_in", "fall", "wave")
SETS = ("studio", "vault", "street", "boardroom", "stage")
PROPS = ("money_stack", "bars_up", "bars_down", "logo_block", "vault_door", "question_mark", "coin_rain")
MAX_PROPS = 4
ENV_RATE = 50  # envelope samples per second of audio

# Keyword rules, first match wins. Order matters: bad news beats good news in a mixed sentence.
RULES: list[tuple[str, str, str, list[str]]] = [  # (pattern, action, set, props)
    (r"bankrupt|collaps|crash|plunge|lost|loss|fell|fall|wiped|debt|default|fired|layoff|scandal|fraud",
     "fall", "street", ["bars_down"]),
    (r"\?|why|how did|mystery|question|nobody knew|puzzle", "think", "studio", ["question_mark"]),
    (r"record|soar|surge|boom|billion|richest|won|wins|comeback|rose|jump|doubled|tripled|profit",
     "celebrate", "stage", ["bars_up", "coin_rain"]),
    (r"vault|cash|reserve|savings|bank|treasury", "point", "vault", ["money_stack", "vault_door"]),
    (r"ceo|board|investor|shareholder|decision|merger|acquire|deal|meeting", "present", "boardroom", ["logo_block"]),
    (r"but|however|surpris|suddenly|shock|unexpected|twist", "shock", "studio", []),
    (r"maybe|perhaps|estimate|unclear|not sure|depends", "shrug", "studio", []),
]
DEFAULT_ROTATION = ("present", "point", "walk_in", "wave")  # used when no keyword matches (varied, not random)


def validate(scene: dict, where: str) -> list[str]:
    """Problems with a host scene's own fields (action, set, props); empty when fine."""
    p: list[str] = []
    if scene.get("action", "present") not in ACTIONS:
        p.append(f"{where}: host action {scene.get('action')!r} not in {list(ACTIONS)}")
    if scene.get("set", "studio") not in SETS:
        p.append(f"{where}: host set {scene.get('set')!r} not in {list(SETS)}")
    props = scene.get("props", [])
    if not isinstance(props, list) or len(props) > MAX_PROPS:
        return p + [f"{where}: host props must be a list of at most {MAX_PROPS}"]
    for i, pr in enumerate(props, 1):
        name = pr.get("kind") if isinstance(pr, dict) else pr
        if name not in PROPS:
            p.append(f"{where}: host prop {i} {name!r} not in {list(PROPS)}")
        elif isinstance(pr, dict) and pr.get("figure") and not scene.get("source_ids"):
            p.append(f"{where}: a prop showing a figure needs scene source_ids (every figure needs a source)")
    return p


def choose(seg: dict, pos: int = 1) -> dict:
    """Pick action, set and props for a segment from its narration (generic shapes only, never real logos)."""
    text = f"{seg.get('chapter', '')} {seg.get('narration', '')}".lower()
    for pattern, action, set_, props in RULES:
        if re.search(pattern, text):
            return {"action": action, "set": set_, "props": list(props)}
    return {"action": DEFAULT_ROTATION[pos % len(DEFAULT_ROTATION)], "set": "studio", "props": []}


def make_scene(seg: dict, pos: int, mascot: dict | None) -> dict:
    """A host scene for a segment with no scene of its own."""
    scene = {"kind": "host", "title": seg.get("chapter", ""), **choose(seg, pos)}
    if mascot:
        scene["mascot"] = dict(mascot)
    return scene


def prop_names(scene: dict) -> list[str]:
    """Prop kinds of a scene (props may be plain strings or {kind, label} objects)."""
    return [p.get("kind") if isinstance(p, dict) else p for p in scene.get("props", [])]


def _synthetic(n: int) -> list[float]:
    """Stand-in mouth movement (about 4 syllables a second at 1/ENV_RATE) when the audio cannot be read."""
    return [0.5 + 0.5 * ((i // 6) % 2) * (0.6 + 0.4 * ((i * 7) % 5) / 4) for i in range(n)]


def envelope(audio, seconds: float, fps: int, ffmpeg: str = "ffmpeg") -> list[float]:
    """Mouth openness 0..1 for each video frame from the narration's loudness. Falls back to a gentle pattern.

    Decodes the audio to 8 kHz mono PCM with ffmpeg, takes the RMS per frame, and scales by the loud-speech level.
    """
    n = max(1, round(seconds * fps))
    if audio is None:
        return _synthetic(n)
    try:
        raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio), "-t", f"{seconds:.3f}", "-ac", "1", "-ar",
                              "8000", "-f", "s16le", "-"], capture_output=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return _synthetic(n)
    pcm = array.array("h")
    pcm.frombytes(raw[: len(raw) // 2 * 2])
    if not pcm:
        return _synthetic(n)
    per = max(1, 8000 // fps)
    rms = []
    for i in range(n):
        chunk = pcm[i * per:(i + 1) * per]
        rms.append((sum(x * x for x in chunk) / len(chunk)) ** 0.5 if chunk else 0.0)
    top = sorted(rms)[int(len(rms) * 0.9)] or max(rms) or 1.0
    return [round(min(1.0, r / top), 3) if r > top * 0.08 else 0.0 for r in rms]
