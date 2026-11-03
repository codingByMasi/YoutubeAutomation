"""Narration styles: how a channel's script is written and how its narrator sounds, in one selectable place.

A style carries (a) writing rules that go into the script prompt, (b) the offline Kokoro narrator voice and speed,
(c) per-emotion rate/pitch offsets and (d) a words-per-second pace. A channel picks one with its `narration` field;
blank means the channel type's default (history = comic_storyteller, business/general = calm_explainer,
kids = warm_singsong). Per-character voices for the cast live in `studio/providers/voices.py`, not here.

Evidence for the comic style: transcripts of the three reference videos (first 3 minutes each) run at about
2.5 words/s (OverSimplified Punic War) to 3.2 words/s (Extra History); OverSimplified swaps to a spoken
character line every 5-15 s, uses modern slang and deadpan understatement; our first history sample ran at about
2.1 words/s with 4 character lines in 58 s and no jokes.
"""

from __future__ import annotations

from studio.errors import StudioError

DEFAULT_FOR_PACK = {"history": "comic_storyteller", "explainer": "calm_explainer", "kids": "warm_singsong",
                    "general": "calm_explainer"}

STYLES: dict[str, dict] = {
    "comic_storyteller": {
        "label": "Comic storyteller",
        "best_for": "History, mythology, 'how it all went wrong' stories, animated casts (OverSimplified style)",
        "wps": 2.8, "kokoro": "am_adam", "speed": 1.08,
        "voice": {"hook": {"rate": 8, "pitch": 1, "volume": 2}, "neutral": {"rate": 2, "pitch": 0, "volume": 0},
                  "reveal": {"rate": -6, "pitch": -1, "volume": 1}, "tense": {"rate": -2, "pitch": -2, "volume": -2},
                  "warm": {"rate": 0, "pitch": 1, "volume": 0}, "excited": {"rate": 10, "pitch": 3, "volume": 3},
                  "pauses": {"before_reveal": 0.35, "after_plant": 0.2, "chapter": 0.5}},
        "rules": [
            "Voice: a quick, casual friend retelling the story at a party. Contractions always. Plain modern words "
            "('pretty mad', 'a terrible idea', 'gets stuck'); never textbook phrasing.",
            "Deadpan understatement and a punchline every 10-15 seconds: state something absurd flatly, then one short "
            "sentence of reaction. Comedy comes from the situation and the stakes, never from changing a fact.",
            "Short sentences, 6-14 words, with the occasional two-word zinger ('Big mistake.'). Brisk pace, about 2.8 "
            "words per second.",
            "Talk to the viewer now and then ('Remember him?', 'Spoiler: it goes badly'). Use 'so', 'and then', "
            "'except', 'but of course' to chain events.",
            "Characters talk. Most skit segments carry 3-6 short spoken lines in `speech` (3-12 words each) that argue,"
            " boast or misunderstand each other, in the same casual modern voice; the narrator sets the scene in one "
            "sentence and then steps back. Aim for a spoken exchange at least every 20 seconds.",
            "Sound-effect words and one-word reactions are allowed in `speech` ('Gasp!', 'Oops.') but keep each under "
            "four words.",
            "Explain causes with a quick 'Because...' chain, not a lecture. Nothing is explained for more than 25 "
            "seconds without a joke, a character line or a turn.",
            "Real dates and numbers stay accurate; anachronism lives only in tone and character banter.",
        ],
    },
    "calm_explainer": {
        "label": "Calm explainer",
        "best_for": "Finance, business, economics, tech and science explainers; anything number-led",
        "wps": 2.5, "kokoro": "bm_george", "speed": 1.0,
        "voice": {"hook": {"rate": 4, "pitch": 0, "volume": 0}, "neutral": {"rate": 0, "pitch": 0, "volume": 0},
                  "reveal": {"rate": -8, "pitch": -2, "volume": 0}, "tense": {"rate": -4, "pitch": -3, "volume": -3},
                  "warm": {"rate": -2, "pitch": 1, "volume": 0}, "excited": {"rate": 5, "pitch": 2, "volume": 2},
                  "pauses": {"before_reveal": 0.55, "after_plant": 0.35, "chapter": 0.7}},
        "rules": [
            "Voice: a clear, confident colleague who respects the viewer's time. Plain words, no jargon without a "
            "one-line definition.",
            "One idea per sentence, 10-18 words. Lead with the number or the contradiction, then explain it.",
            "Light dry humour is fine, once or twice a minute at most; never sarcasm about money lost by real people.",
            "Use 'you' and one concrete running example. Pause (a short sentence) before every key number.",
            "Estimates are worded as estimates ('about', 'roughly').",
        ],
    },
    "warm_singsong": {
        "label": "Warm sing-song",
        "best_for": "Toddlers and preschoolers: stories, rhymes, counting, songs",
        "wps": 2.0, "kokoro": "af_heart", "speed": 0.92,
        "voice": {"hook": {"rate": 4, "pitch": 4, "volume": 3}, "neutral": {"rate": -4, "pitch": 3, "volume": 2},
                  "reveal": {"rate": -2, "pitch": 5, "volume": 4}, "tense": {"rate": -4, "pitch": 2, "volume": 0},
                  "warm": {"rate": -6, "pitch": 3, "volume": 0}, "excited": {"rate": 4, "pitch": 6, "volume": 4},
                  "pauses": {"before_reveal": 0.0, "after_plant": 0.0, "chapter": 0.4}},
        "rules": [
            "Voice: a gentle, smiling grown-up reading to a child. Sentences of 3-8 words, simple words, rhythm you "
            "could clap to.",
            "Repeat key lines (the refrain) three times; use call-and-response ('Can you wave? Wave, wave, wave!') "
            "and leave a beat for the child to answer.",
            "Name feelings and sounds ('Splash!', 'Hooray!'). Nothing scary; every problem is tiny and solved.",
        ],
    },
    "dramatic_documentary": {
        "label": "Dramatic documentary",
        "best_for": "Serious history, war, biography, geopolitics (Extra History style)",
        "wps": 3.0, "kokoro": "bm_lewis", "speed": 1.0,
        "voice": {"hook": {"rate": 2, "pitch": -1, "volume": 0}, "neutral": {"rate": 0, "pitch": 0, "volume": 0},
                  "reveal": {"rate": -8, "pitch": -3, "volume": 1}, "tense": {"rate": -5, "pitch": -4, "volume": -2},
                  "warm": {"rate": -3, "pitch": 0, "volume": 0}, "excited": {"rate": 4, "pitch": 1, "volume": 2},
                  "pauses": {"before_reveal": 0.7, "after_plant": 0.4, "chapter": 0.9}},
        "rules": [
            "Voice: an earnest storyteller who makes you care about one person. Vivid, concrete detail; sentences of "
            "12-22 words with the odd long, flowing one.",
            "Humour is rare and dry. Build to turns: 'But...' moves the story at every chapter end.",
            "Human cost is stated plainly in one sentence, never graphically.",
        ],
    },
    "hushed_suspense": {
        "label": "Hushed suspense",
        "best_for": "True crime, mysteries, disasters, unsolved cases",
        "wps": 2.3, "kokoro": "bm_daniel", "speed": 0.94,
        "voice": {"hook": {"rate": -2, "pitch": -2, "volume": -1}, "neutral": {"rate": -2, "pitch": -1, "volume": -1},
                  "reveal": {"rate": -10, "pitch": -4, "volume": 0}, "tense": {"rate": -6, "pitch": -4, "volume": -3},
                  "warm": {"rate": -4, "pitch": 0, "volume": -1}, "excited": {"rate": 2, "pitch": 0, "volume": 1},
                  "pauses": {"before_reveal": 0.9, "after_plant": 0.5, "chapter": 0.9}},
        "rules": [
            "Voice: low, calm, close to the microphone. Short and medium sentences, facts first, speculation labelled.",
            "Withhold: plant a question, delay the answer by one beat. Respect victims; no graphic detail.",
        ],
    },
    "high_energy_hype": {
        "label": "High-energy hype",
        "best_for": "Gaming, tech reviews, challenges, reactions, top-10 lists",
        "wps": 3.1, "kokoro": "am_puck", "speed": 1.15,
        "voice": {"hook": {"rate": 10, "pitch": 3, "volume": 4}, "neutral": {"rate": 5, "pitch": 1, "volume": 1},
                  "reveal": {"rate": -2, "pitch": 2, "volume": 3}, "tense": {"rate": 2, "pitch": 0, "volume": 0},
                  "warm": {"rate": 3, "pitch": 2, "volume": 1}, "excited": {"rate": 12, "pitch": 5, "volume": 5},
                  "pauses": {"before_reveal": 0.25, "after_plant": 0.1, "chapter": 0.3}},
        "rules": [
            "Voice: an excited friend. Very short sentences, a new picture every 2-4 seconds, a hook in the first "
            "3 seconds. Slang is fine; keep claims honest.",
            "Count things ('Number three is wild.') and promise a payoff you deliver.",
        ],
    },
    "motivational_coach": {
        "label": "Motivational coach",
        "best_for": "Self-improvement, habits, productivity, life lessons",
        "wps": 2.6, "kokoro": "am_michael", "speed": 1.0,
        "voice": {"hook": {"rate": 4, "pitch": 0, "volume": 2}, "neutral": {"rate": 0, "pitch": 0, "volume": 0},
                  "reveal": {"rate": -8, "pitch": -2, "volume": 2}, "tense": {"rate": -3, "pitch": -2, "volume": 0},
                  "warm": {"rate": -2, "pitch": 1, "volume": 1}, "excited": {"rate": 6, "pitch": 2, "volume": 3},
                  "pauses": {"before_reveal": 0.5, "after_plant": 0.3, "chapter": 0.6}},
        "rules": [
            "Voice: a direct, warm coach. Second person ('you'), one story or study per point, one action for today.",
            "Repeat the core line twice, differently. No medical or income promises.",
        ],
    },
}

IDS = tuple(STYLES)


def check(style_id: str) -> str:
    """Return a valid style id ('' allowed = type default) or raise a StudioError that says what to pick."""
    sid = (style_id or "").strip().lower()
    if sid and sid not in STYLES:
        raise StudioError(f"'{style_id}' is not a narration style.", f"Choose one of: {', '.join(IDS)}.",
                          "Set the channel's narration style again.")
    return sid


def resolve(pack: str, chosen: str = "") -> str:
    """The style id in force: the channel's choice, else the pack's default."""
    return check(chosen) or DEFAULT_FOR_PACK.get(pack, "calm_explainer")


def prompt_block(style_id: str) -> str:
    """The narration-style section of a script prompt."""
    s = STYLES[style_id]
    rules = "\n".join(f"- {r}" for r in s["rules"])
    return f"# Narration style: {s['label']}\n{rules}\n"


def guide_table() -> str:
    """Markdown list of every style and what it suits (used by the docs and the app)."""
    return "\n".join(f"- **{s['label']}** (`{k}`): {s['best_for']}." for k, s in STYLES.items())
