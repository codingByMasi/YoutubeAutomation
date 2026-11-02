"""Cliche, hype and filler phrases that must not appear in titles or narration (lower case, straight quotes)."""

from __future__ import annotations

import re

BANNED_PHRASES: list[str] = [
    # hype and clickbait the platform and viewers punish
    "you won't believe", "shocking", "guaranteed", "secret they don't want you to know", "get rich",
    "mind-blowing", "mind blowing", "jaw-dropping", "game-changer", "game changer", "life-changing",
    "what happens next will", "doctors hate", "this one weird trick", "nobody is talking about",
    "they don't want you to know", "will blow your mind", "changes everything forever",
    # filler openers and throat-clearing
    "in today's video", "in this video we", "in this video, we", "welcome back to the channel",
    "hey guys", "what's up guys", "before we begin", "without further ado", "let's dive in", "let's dive into",
    "let's get started", "buckle up", "grab a coffee", "stay tuned", "make sure to smash", "smash that like",
    "don't forget to subscribe", "hit the bell",
    # filler connectors and cliches in narration
    "at the end of the day", "it goes without saying", "needless to say", "in a nutshell",
    "when all is said and done", "the fact of the matter", "it is important to note", "it's important to note",
    "it's worth noting", "it is worth noting", "in the ever-evolving", "in today's fast-paced world",
    "in the world of", "delve into", "a testament to", "rich tapestry", "navigate the landscape",
    "unlock the secrets", "unlock the power", "take it to the next level", "revolutionize the way",
    # finance-specific danger
    "financial advice", "risk-free", "risk free", "can't lose", "sure thing", "to the moon",
]

# Phrases that are fine in a disclaimer line, so the not-financial-advice sentence is not flagged.
ALLOWED_CONTEXT = ("not financial advice", "this is not financial advice", "isn't financial advice")


def banned_in(text: str, extra: list[str] | None = None) -> list[str]:
    """Banned phrases found in text (case and curly-apostrophe insensitive)."""
    low = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    for ok in ALLOWED_CONTEXT:
        low = low.replace(ok, " ")
    return [p for p in [*BANNED_PHRASES, *(extra or [])] if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", low)]
