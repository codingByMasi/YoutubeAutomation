"""Host-character scenes: the channel mascot acts out a script beat in a small 3D set.

Pure Python (no Blender): validation, choosing an action/set/props from the narration, and a loudness envelope of the
narration audio so the mouth moves with the voice. The Blender side lives in `studio/blender/scene_script.py`.
"""

from __future__ import annotations

import array
import re
import subprocess
import sys
from pathlib import Path

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


MODEL_EXTS = (".glb", ".gltf")  # glTF is what Kenney, Quaternius and KayKit ship; Blender imports it natively
# Which clip names suit each action (lower-case substrings, tried in order). The channel can override per action
# with mascot["clips"] = {"point": "Interact"}. A model with none of these falls back to its first clip.
CLIP_WORDS = {
    "present": ("idle", "interact", "talk"), "point": ("point", "interact", "idle"),
    "celebrate": ("cheer", "victory", "dance", "jump", "wave"), "shock": ("hit", "scare", "jump", "idle"),
    "think": ("think", "idle"), "shrug": ("shrug", "idle"), "walk_in": ("walk", "run", "sprint"),
    "fall": ("die", "fall", "death", "knock"), "wave": ("wave", "interact", "idle"),
}
_noted: set[str] = set()


def resolve_model(mascot: dict | None, assets_dir: Path | None) -> str:
    """Absolute path of the mascot's glTF model, or "" (shapes are used) when none is set or the file is missing.

    A relative `model` is looked up in `<assets>/characters/` then `<assets>/`. Missing files print one note.
    """
    name = str((mascot or {}).get("model") or "").strip()
    if not name:
        return ""
    cands = [Path(name)] if Path(name).is_absolute() else (
        [assets_dir / "characters" / name, assets_dir / name] if assets_dir else [])
    for c in cands:
        if c.suffix.lower() in MODEL_EXTS and c.is_file():
            return str(c.resolve())
    if name not in _noted:
        _noted.add(name)
        print(f"Note: character model {name!r} was not found (looked in assets/characters); using the built-in "
              "shapes instead. Put a .glb file there or clear the mascot 'model' field.", file=sys.stderr)
    return ""


def with_model(scene: dict, assets_dir: Path | None) -> dict:
    """The scene with its mascot's `model` resolved to a real path (or removed) so Blender can load it."""
    mascot = scene.get("mascot") or {}
    if not mascot.get("model"):
        return scene
    return {**scene, "mascot": {**mascot, "model": resolve_model(mascot, assets_dir)}}
