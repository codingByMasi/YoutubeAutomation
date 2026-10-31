"""Kids script stage: writes the prompt file, validates the answer, saves script.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

from studio import llm
from studio.context import Ctx
from studio.errors import StudioError
from studio.kids import spec


def slugify(topic: str) -> str:
    """Folder-safe name for a kids project."""
    s = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    if not s:
        raise StudioError("The topic is empty.", "A project folder name is built from the topic.",
                          "Pass a topic such as 'counting ducks'.")
    return s


def project_dir(ctx: Ctx, slug: str) -> Path:
    d = ctx.settings.projects_dir / f"kids_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_prompt(topic: str) -> str:
    """The rules and exact JSON shape Claude Code must follow."""
    shape = {
        "title": "Counting Five Little Ducks (short, under 60 chars)",
        "description": "Plain sentence for parents. Say it is an original song.",
        "tags": ["counting for kids", "nursery rhyme"],
        "kind": f"one of {spec.KINDS}",
        "source": "original | public_domain",
        "source_note": "Required if public_domain: the rhyme, where the words come from, why they are public domain.",
        "scenes": [{
            "kind": "verse | chorus",
            "lines": [f"1-{spec.MAX_LINES_PER_SCENE} lines, each up to {spec.MAX_WORDS_PER_LINE} words"],
            "visual": {"background": f"one of {spec.BACKGROUNDS}", "motion": f"one of {spec.MOTIONS}",
                       "characters": f"list from {spec.CHARACTERS}", "count": "1-10; how many appear"},
        }],
    }
    return f"""# Task: write a children's song video script about "{topic}"

Audience: ages 2 to 5. Output is a short sing-along video made of simple animated scenes.

## Rules (the validator rejects breaches)
- Write ORIGINAL words. A very old traditional rhyme (public domain text only) is allowed: set
  `source` to public_domain and fill `source_note`. Never reuse modern arrangements, lyrics or
  characters from any existing channel or franchise (no Cocomelon, Pinkfong, Bluey, Disney, etc.).
- At least {spec.MIN_SCENES} scenes. Use a chorus scene (kind=chorus) at least twice with IDENTICAL lines.
- Short, rhythmic, rhyming lines. Repetition is good for learning (counting up, colours, animals).
- Positive, gentle content only: no fear, violence, danger games, product placement or calls to
  buy, click or subscribe aimed at children.
- Teach one clear thing (a number sequence, colour names, animal sounds, a bedtime routine).
- Visuals use only the fixed vocabulary in the shape below; the renderer draws simple shapes.
- Each scene's `count` is how many characters appear; for counting songs match it to the lyric.

## JSON shape (write ONLY this object)
```json
{json.dumps(shape, indent=2)}
```
"""


def run(ctx: Ctx, topic: str, force: bool = False) -> dict:
    """Return the validated kids script for `topic`, saving projects/kids_<slug>/script.json."""
    slug = slugify(topic)
    d = project_dir(ctx, slug)
    data = llm.ask_json(ctx.settings, d, "kids_script", build_prompt(topic), validate=spec.validate, force=force)
    data["slug"] = slug
    (d / "script.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
