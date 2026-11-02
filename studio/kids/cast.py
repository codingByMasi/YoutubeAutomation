"""Reference cast for kids channels: a registry of recurring original characters.

Each character is one JSON file in `studio/kids/roster/` (built in) or `assets/kids/roster/` (your own; same id
overrides a built-in one). To add a character, drop in a JSON file with: id, name, species, role, personality,
catchphrase, main (hex), accent (hex), look, rhymes, shape (silhouette note), voice (see
studio/providers/voices.py: edge name, rate, pitch, kokoro id, speed; missing keys use a neutral default).
Add `"builder": "<id>"` only if rhyme_cast.py has a hand-made 3D model for it; without one the 3D renderer draws a
generic round character in your colours and the 2D renderer a round character with a face. A 2D sprite is
`studio/kids/cast/<id>.svg` (four groups, see sprites.py); without one the code-drawn round friend is used.
A channel picks its cast with the `kids_cast` profile field (list of ids; empty means the whole roster).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from studio.errors import StudioError
from studio.providers import voices

BUILTIN = Path(__file__).parent / "roster"
_extra_dirs: list[Path] = []
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID = re.compile(r"^[a-z][a-z0-9_]{1,23}$")
REQUIRED = ("id", "name", "species", "personality", "main", "accent")


def add_dir(path: Path) -> None:
    """Also read characters from `path` (your own roster folder). Safe to call repeatedly."""
    if path not in _extra_dirs:
        _extra_dirs.append(path)


def check(entry: dict, source: str = "character") -> dict:
    """Return a cleaned entry or raise a StudioError that says what to fix."""
    if not isinstance(entry, dict):
        raise StudioError(f"{source} is not a JSON object.", "A character file holds one object.",
                          "Fix the file or delete it.")
    missing = [k for k in REQUIRED if not str(entry.get(k, "")).strip()]
    if missing:
        raise StudioError(f"{source} is missing {', '.join(missing)}.", f"Required: {', '.join(REQUIRED)}.",
                          "Add the missing fields to the character file.")
    if not _ID.match(entry["id"]):
        raise StudioError(f"{source}: '{entry['id']}' is not a valid id.",
                          "Use 2-24 lowercase letters, digits or _, starting with a letter.", "Change the id.")
    for k in ("main", "accent"):
        if not _HEX.match(entry[k]):
            raise StudioError(f"{source}: {k} '{entry[k]}' is not a colour.", "Colours look like #9A6234.",
                              f"Fix {k}.")
    out = {"role": "", "catchphrase": "", "look": "", "rhymes": [], "builder": "", "shape": "", **entry}
    out["voice"] = voices.check(entry.get("voice") or {}, source)
    out["rhymes"] = [str(r) for r in out["rhymes"]]
    return out


def _read(folder: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise StudioError(f"{f.name} is not valid JSON.", str(exc), "Fix or delete the file.") from exc
        e = check(e, f.name)
        found[e["id"]] = e
    return found


def load() -> dict[str, dict]:
    """Every character by id: built-in first, then your own folders (which may override)."""
    out = _read(BUILTIN)
    for d in _extra_dirs:
        out.update(_read(d))
    return out


def ids() -> list[str]:
    """All character ids, usable in a kids script's `visual.characters`."""
    return list(load())


def for_channel(profile: dict) -> list[dict]:
    """The channel's cast: its `kids_cast` ids (unknown ids are an error), or the whole roster when empty."""
    roster = load()
    want = list(profile.get("kids_cast") or [])
    unknown = [w for w in want if w not in roster]
    if unknown:
        raise StudioError(f"Unknown kids character(s): {', '.join(unknown)}.", f"Known: {', '.join(roster)}.",
                          "Fix the channel's kids_cast list or add the character file.")
    return [roster[w] for w in want] if want else list(roster.values())


def brief(cast: list[dict]) -> str:
    """Prompt text describing the recurring cast so scripts use them with consistent personalities."""
    lines = [f"- `{c['id']}`: {c['name']}, a {c['species']}. {c['personality']} Suits: {', '.join(c['rhymes'])}."
             for c in cast]
    return ("Recurring cast (original characters; prefer them in `visual.characters` so children meet the same "
            "friends each video; use others only when the song needs them):\n" + "\n".join(lines))


def blender_cast(names: list[str]) -> dict:
    """Colours and 3D builder keys for the characters named, handed to scene_script.py."""
    roster = load()
    return {n: {"main": roster[n]["main"], "accent": roster[n]["accent"], "builder": roster[n]["builder"]}
            for n in dict.fromkeys(names) if n in roster}


def voice_for(char_id: str) -> dict:
    """The character's voice settings (see `studio.providers.voices`); a neutral default for unknown ids."""
    c = load().get(char_id)
    return c["voice"] if c else dict(voices.DEFAULT)
