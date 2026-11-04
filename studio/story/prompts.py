"""Prompt composition for the story engine: pack lookup with fallback, and the shared placeholder values."""

from __future__ import annotations

import json
import re
from pathlib import Path

from studio.errors import StudioError
from studio.story import photo

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


def shape(prof: dict | None = None) -> str:
    """The output JSON shape; cartoon packs (history, kids) draw scenes, so keywords are not 'photographable'."""
    text = read("_shape").replace("{{", "{").replace("}}", "}")
    if prof and prof.get("pack") in ("history", "kids"):
        text = text.replace("concrete photographable terms", "short scene terms (what is drawn)")
    return text


def _cast_block(prof: dict) -> str:
    if not prof.get("cast"):
        return ""
    from studio.history import cast
    return cast.prompt_block(prof)


def _narration_block(prof: dict) -> str:
    from studio.story import narration_styles as narration
    return narration.prompt_block(prof["narration"]) if prof.get("narration") in narration.STYLES else ""


def compose(name: str, prof: dict, **values) -> str:
    """Fill a pack prompt. Unknown placeholders become empty; profile-derived blocks are added automatically."""
    vals = _Safe(
        banned=", ".join(f'"{p}"' for p in prof["banned_phrases"]), min_minutes=prof["min_minutes"],
        max_minutes=prof["max_minutes"], compliance=" ".join(prof["compliance"]), ending_style=prof["ending_style"],
        writing_rules=writing_rules(prof), exemplar=exemplar(prof["pack"]), shape=shape(prof),
        hooks=read("hooks", prof["pack"]), photo_rule=photo.prompt_rule(prof["pack"]),
        cast_block=_cast_block(prof), narration_block=_narration_block(prof), tone=prof.get("tone", ""),
        recent="(no earlier videos on this channel yet)", facts_block="(none)")
    vals.update(values)
    from studio.story import style
    for key in ("style", "brief"):
        style.check_no_placeholders(str(vals.get(key, "")), f"channel {key}")
    from studio.story.profile import short_form_note
    return read(name, prof["pack"]).format_map(vals) + short_form_note(prof)


SOURCE_ASK = re.compile(
    r"\bsources?\b|\bcit(?:e|es|ed|ation|ations)\b|fact[_ ]?ids?\b|source_(?:ids?|url)|quote_snippet|url_or_note", re.I)


# Field names only an old prompt template asked for. Plain words like "source" can appear in a topic or in facts
# ("sources of revenue"), so they must never make a saved prompt look stale.
OLD_SOURCE_FIELDS = re.compile(
    r"source_(?:ids?|url)|fact[_ ]?ids\b|quote_snippet|url_or_note|`sources?`|public source", re.I)


def is_old_source_prompt(text: str) -> bool:
    """True if a saved prompt was written by an older version that asked for source fields."""
    return bool(OLD_SOURCE_FIELDS.search(text or ""))


def asks_for_sources(text: str) -> bool:
    """True if a prompt still asks for sources, citations or fact ids (owner decision: scripts carry none)."""
    return bool(SOURCE_ASK.search(text or ""))


def j(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)
