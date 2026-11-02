"""Prompt composition for the story engine: pack lookup with fallback, and the shared placeholder values."""

from __future__ import annotations

import json
from pathlib import Path

from studio.errors import StudioError

BASE = Path(__file__).resolve().parent.parent / "prompts"


class _Safe(dict):
    def __missing__(self, key: str) -> str:  # unknown placeholders render empty instead of raising
        return ""


def read(name: str, pack: str = "explainer") -> str:
    """studio/prompts/<pack>/<name>.md, falling back to studio/prompts/<name>.md (the explainer files)."""
    for p in (BASE / pack / f"{name}.md", BASE / f"{name}.md"):
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise StudioError(f"Prompt file {name}.md not found for pack {pack!r}.", "", "Restore studio/prompts/.")


def exemplar(pack: str) -> str:
    p = BASE / "exemplars" / f"{pack}.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "(none)"


def writing_rules(prof: dict) -> str:
    """The shared writing rules with this profile's numbers filled in."""
    wps = prof["wps"]
    every = prof.get("analogy_every_seconds") or 0
    return read("_writing", "explainer").format_map(_Safe(
        sentence_cap=prof["sentence_max_words"], analogy_every=every or 120, wps=wps,
        analogy_note="" if every else " (not needed for this audience: repetition and rhythm do the work)",
        hook_seconds=15 if not prof.get("kids") else 8, min_minutes=prof["min_minutes"],
        max_minutes=prof["max_minutes"], min_words=int(prof["min_minutes"] * 60 * wps),
        max_words=int(prof["max_minutes"] * 60 * wps), banned=", ".join(f'"{p}"' for p in prof["banned_phrases"])))


def shape() -> str:
    return read("_shape").replace("{{", "{").replace("}}", "}")


def _cast_block(prof: dict) -> str:
    if not prof.get("cast"):
        return ""
    from studio.history import cast
    return cast.prompt_block(prof)


def compose(name: str, prof: dict, **values) -> str:
    """Fill a pack prompt. Unknown placeholders become empty; profile-derived blocks are added automatically."""
    vals = _Safe(
        banned=", ".join(f'"{p}"' for p in prof["banned_phrases"]), min_minutes=prof["min_minutes"],
        max_minutes=prof["max_minutes"], compliance=" ".join(prof["compliance"]), ending_style=prof["ending_style"],
        writing_rules=writing_rules(prof), exemplar=exemplar(prof["pack"]), shape=shape(),
        hooks=read("hooks", prof["pack"]), cast_block=_cast_block(prof), tone=prof.get("tone", ""),
        recent="(no earlier videos on this channel yet)", facts_block="(none)")
    vals.update(values)
    return read(name, prof["pack"]).format_map(vals)


def j(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)
