# ruff: noqa: E501  (keyword lists)
"""Eras for the history channel: which period a story is set in, so characters dress for it.

An era only picks the clothing style the per-character drawer (`studio.history.figures.ERA_STYLE`) falls back to when
the script's own description of a character says nothing about clothes. Era ids are the keys of `OUTFITS`; each has
topic keywords so the studio can guess the era from the title. Original data only."""

from __future__ import annotations

import re

DEFAULT = "default"

# Each era: name and keywords (topic words that suggest it).
OUTFITS: dict[str, dict] = {
    "roman": {
        "name": "Ancient Rome",
        "keywords": ("rome", "roman", "caesar", "legion", "punic", "carthage", "hannibal", "augustus", "republic", "gladiator", "pompey", "senate"),
    },
    "greek": {
        "name": "Ancient Greece",
        "keywords": ("greece", "greek", "athens", "sparta", "spartan", "alexander", "persian wars", "marathon", "thermopylae", "pericles", "macedon"),
    },
    "viking": {
        "name": "Norse / Viking",
        "keywords": ("viking", "norse", "norway", "scandinav", "odin", "thor", "valhalla", "ragnar", "danelaw", "longship", "iceland", "lindisfarne", "saga"),
    },
    "medieval": {
        "name": "Medieval",
        "keywords": ("medieval", "middle ages", "crusade", "knight", "feudal", "castle", "plague", "black death", "charlemagne", "norman", "hundred years", "magna carta", "monastery"),
    },
    "desert": {
        "name": "Desert / Silk Road",
        "keywords": ("arab", "caliph", "islamic", "baghdad", "desert", "silk road", "caravan", "ottoman", "mamluk", "bedouin", "saladin", "mongol", "timur", "persia", "sultan", "mecca", "sahara"),
    },
    "egyptian": {
        "name": "Ancient Egypt",
        "keywords": ("egypt", "pharaoh", "pyramid", "nile", "cleopatra", "tutankhamun", "ramses", "sphinx", "mesopotamia", "babylon", "sumer"),
    },
    "samurai": {
        "name": "Feudal Japan",
        "keywords": ("japan", "samurai", "shogun", "edo", "tokugawa", "meiji", "ninja", "sengoku", "kyoto", "tokyo", "nobunaga", "china", "han dynasty", "ming", "qing", "tang dynasty", "dynasty", "imperial china", "korea"),
    },
    "renaissance": {
        "name": "Renaissance",
        "keywords": ("renaissance", "medici", "florence", "venice", "leonardo", "michelangelo", "gutenberg", "printing press", "machiavelli", "fugger", "bank", "banking", "tudor", "elizabeth", "henry viii", "reformation", "luther"),
    },
    "sail": {
        "name": "Age of Sail",
        "keywords": ("pirate", "navy", "age of sail", "colonial", "east india", "trafalgar", "armada", "empire", "slave trade", "columbus", "magellan", "revolution", "napoleon", "waterloo", "american revolution", "french revolution", "trade company", "opium"),
    },
    "modern": {
        "name": "Modern 1900s",
        "keywords": ("world war", "wwi", "wwii", "ww1", "ww2", "great war", "trench", "nazi", "soviet", "cold war", "1914", "1939", "industrial", "railway", "telegraph", "great depression", "stock market", "oil", "cold-war", "vietnam", "korean war"),
    },
}

ERAS = tuple(OUTFITS)


def known(outfit: str | None) -> bool:
    """True for the default outfit (None, '' or 'default') and every era in `OUTFITS`."""
    return (outfit or DEFAULT) == DEFAULT or outfit in OUTFITS


def guess_era(text: str) -> str:
    """Best-matching era id for a topic/title/narration text, or the default when nothing matches.

    Whole words or word starts only, so 'bank' does not fire inside 'embankment'. Ties go to the first era listed."""
    low = (text or "").lower()
    best, best_n = DEFAULT, 0
    for eid, o in OUTFITS.items():
        n = sum(1 for k in o["keywords"] if re.search(rf"(?<![a-z]){re.escape(k)}", low))
        if n > best_n:
            best, best_n = eid, n
    return best


def era_for(seg: dict, pkg: dict | None = None) -> str:
    """The outfit for one segment: its own `era`, else the video's `era`, else a guess from the title, else default.

    Old scripts have no `era` and a title that matches nothing, so they keep the default look."""
    for src in (seg, pkg or {}):
        e = str(src.get("era") or "").strip().lower()
        if e:
            return e if known(e) else DEFAULT
    return guess_era(_title_of(pkg or {}))


def _title_of(pkg: dict) -> str:
    """The video's title for era guessing: `title`, else the picked entry of `titles`, else the topic.
    (Scripts store `titles` and `topic`, not `title`, so a guess from `title` alone never found anything.)"""
    if pkg.get("title"):
        return str(pkg["title"])
    titles = [t for t in pkg.get("titles") or [] if isinstance(t, dict) and t.get("text")]
    pick = next((t for t in titles if t.get("is_pick")), titles[0] if titles else None)
    return str(pick["text"] if pick else pkg.get("topic") or "")


def prompt_line() -> str:
    """One line for the planner and script prompts that lists the eras the writer may choose."""
    return ("Costumes: characters dress for the story. Set a top-level `era` "
            f"(one of {', '.join(ERAS)}, or {DEFAULT}) and, only when the story jumps to another period, an `era` on "
            "that segment. Leave it out to let the studio guess from the title.")
