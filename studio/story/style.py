# ruff: noqa: E501
"""Type-specific style guides for prompts, and the guard that stops unfilled placeholders reaching a prompt.

The finance (explainer) pack reads SPEC.md section 9; history, kids and general packs have their own guides here so
money-flow wording never leaks into them.
"""

from __future__ import annotations

import re

from studio.errors import StudioError

# Template leftovers that must never reach an LLM prompt.
PLACEHOLDER = re.compile(r"\[(?:add more|HEX CODES|FONT NAME|e\.g\.[^\]\n]*|TODO|TBD|fill in[^\]\n]*)\]", re.I)

# Fallbacks for a SPEC.md copy that still has the template placeholders.
SPEC_FILL = {
    "[add more]": "see the banned list under Rules",
    "[HEX CODES]": "the channel's primary and accent colors",
    "[FONT NAME]": "the channel's bold heading font",
    "[e.g. calm, light, instrumental]": "calm, light, instrumental",
}

STYLES: dict[str, str] = {
    "history": """- **Tone:** clear storyteller, cinematic where it matters, light dry humour where it helps; plain English.
  A narrator who cares about the people in the story, not a lecturer.
- **Banned phrases:** see the banned list under Rules.
- **Titles:** under 70 characters; one clear promise; no all-caps shouting; no claim the video can't back up. Preferred
  patterns: "The Rise and Fall of X", "What Really Happened to X", "How X Really Worked", "X: The Whole Story",
  with a concrete date, place or number where the video supports it.
- **Video structure:** cold open inside a scene, title card, rewind to the cause, chapters that each end on a turn,
  one short numbered diagram for "how it worked", a human cost after any big number, an ending that names the next
  threat and points to the next part.
- **Visual rule:** animated scenes with the recurring cartoon cast, maps and timelines for place and time,
  a diagram for any mechanism; archive images only for things (places, documents, objects), at most one per chapter, and only
  on demand. Never a real likeness.
- **Accuracy:** every date and number carries a fact id; name a source when you have one (primary source, museum or archive page,
  reputable article). Label estimates as estimates; mark disputed points as disputed in the narration.
- **Hook:** first 15 seconds drop the viewer into a moment, open a question and promise the payoff; no long intros and
  no "before we start, subscribe".
- **Pacing:** visual change every 3-6 seconds; an open loop every 30-45 seconds; a cliffhanger at every chapter end.
- **Thumbnails:** 1-5 words; one focal figure from the cast; high contrast; the channel's brand colors and heading font.
- **Intro/outro:** under 5 seconds each.
- **Music mood:** tense and cinematic under the story, lighter under jokes; ducked at least 15 dB under voice.
- **Description template:** 2-line summary, chapters, sources, a note that dialogue and likenesses are invented.""",
    "kids": """- **Tone:** warm, playful, slow and clear; tiny words; lots of repetition and call-and-response.
- **Banned phrases:** see the banned list under Rules.
- **Titles:** under 70 characters; the song or character first, the learning goal second ("Counting to 5 with Pip").
- **Video structure:** meet the character, the goal, a small obstacle, try again (repeat), a counting
  or call-and-response moment, a happy resolution, a wave goodbye.
- **Visual rule:** bright, simple 2D characters and objects that match the words; a visual change every 3-5 seconds.
  Never scary, never a real brand or person.
- **Accuracy:** counting facts and animal sounds must be correct; no claims beyond them.
- **Hook:** the character and the first song line within 8 seconds.
- **Pacing:** short sentences, a repeated refrain, a movement or sound cue every few seconds.
- **Thumbnails:** one big cheerful character, 1-3 words, bright colors.
- **Intro/outro:** under 5 seconds each; the outro is a wave goodbye.
- **Music mood:** major key, gentle, singable.
- **Description template:** 1-line summary, lyrics, "Made for Kids".""",
    "general": """- **Tone:** clear, curious, accurate; plain English. Explain like a smart friend, not a lecturer.
- **Banned phrases:** see the banned list under Rules.
- **Titles:** under 70 characters; one clear promise; no all-caps shouting; no claim the video can't back up.
- **Video structure:** hook, why it matters, how it works, a surprising detail, an example, a takeaway.
- **Visual rule:** a diagram or chart for every major figure; footage only illustrates the setting.
- **Accuracy:** name a source in `script.json` when you have one (optional); label estimates as estimates.
- **Hook:** first 15 seconds state the problem and the payoff.
- **Pacing:** visual change every 4-6 seconds; a retention beat every 30-45 seconds.
- **Thumbnails:** 3-5 words max; one focal element; high contrast.
- **Intro/outro:** under 5 seconds each.
- **Music mood:** calm, light, instrumental, ducked at least 15 dB under voice.
- **Description template:** 2-line summary, chapters, sources, links.""",
}


def fill_spec(text: str) -> str:
    """SPEC.md section 9 with any leftover template placeholders replaced by defaults."""
    for k, v in SPEC_FILL.items():
        text = text.replace(", " + k, ", " + v).replace(k, v)
    return text


def for_profile(prof: dict, spec_text: str) -> str:
    """Style guide for a story profile: SPEC section 9 for the finance pack, a built-in guide for the others."""
    pack = prof.get("pack", "explainer")
    return STYLES[pack] if pack in STYLES else fill_spec(spec_text)


def check_no_placeholders(text: str, what: str) -> None:
    """Raise a StudioError if `text` still holds a template placeholder such as [HEX CODES]."""
    m = PLACEHOLDER.search(text or "")
    if m:
        raise StudioError(f"The {what} still has an unfilled placeholder {m.group(0)!r}.",
                          "A template value was never replaced, so the prompt would confuse the writer.",
                          "Replace it in SPEC.md (section 9) or in the channel profile, then re-run.")
