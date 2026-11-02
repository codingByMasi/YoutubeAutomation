"""Story profiles: every length, pacing, voice, loudness and hook number for a channel type, in one place.

A channel type (business/history/kids/general) maps to a prompt pack (explainer/history/kids/general). The
profile holds the pack's defaults; an owner can override any key (and any flag) in the channel profile under
`story` (see `for_channel`). To add a type, see docs/CHANGELOG.md "Adding a channel type".
"""

from __future__ import annotations

import copy
from pathlib import Path

PACK_FOR_TYPE = {"business": "explainer", "general": "general", "history": "history", "kids": "kids"}

# Per-channel-type feature flags. New behaviours default ON; set a flag to false in the channel's `story` override
# (or `studio channels edit --story-flag name=false` via the web setup) to switch one off.
DEFAULT_FLAGS: dict[str, bool] = {
    "word_count_check": True,    # words vs est_seconds and total length range
    "sentence_rules": True,      # sentence cap + rhythm variance + banned phrases (profile list)
    "fact_ledger": True,         # facts.json from story_plan, verified in code, numbers must trace to a fact id
    "loop_ids": True,            # plants_loop / pays_loop with id, spread and distance checks
    "hook_rotation": True,       # never reuse the hook_type of the last 3 videos
    "repetition_ledger": True,   # cross-video structure memory and similarity checks
    "story_review": True,        # task 3: combined critic / swipe-away / rewrite
    "prosody": True,             # per-beat rate/pitch/volume and pauses
    "chapter_tts": True,         # synthesize per chapter, split by word timing
    "caption_sync_check": True,  # gate: caption times vs audio
    "visual_intent": True,       # shot_type / must_show / avoid, no 3 same shots in a row
    "semantic_visuals": False,   # needs optional open_clip / sentence-transformers
    "footage_reuse_ledger": True,
    "mood_music": True,          # per-chapter mood, stingers, drop before the twist
    "title_judge": True,         # deterministic title ranking + promise check
    "feedback_loop": True,       # auto learn after analytics and feed top/bottom hooks into prompts
}

_SHARED = {
    "language": "English", "region": "global", "wps": 2.5, "wps_tolerance": 0.4,
    "lufs_target": -14.0, "true_peak": -1.0, "caption_drift_ms": 250,
    "voice": {  # offsets per emotion: rate %, pitch Hz, volume %
        "hook": {"rate": 6, "pitch": 0, "volume": 0}, "neutral": {"rate": 0, "pitch": 0, "volume": 0},
        "reveal": {"rate": -8, "pitch": -2, "volume": 0}, "tense": {"rate": -4, "pitch": -3, "volume": -3},
        "warm": {"rate": -2, "pitch": 1, "volume": 0}, "excited": {"rate": 6, "pitch": 3, "volume": 3},
        "pauses": {"before_reveal": 0.55, "after_plant": 0.35, "chapter": 0.7},
    },
    "music_moods": {"neutral": "neutral", "tense": "tense", "resolve": "resolve"},
    "drop_before_twist": True, "stinger_on_reveal": True,
    "extra_banned": [], "max_grade": 10,
}

PACKS: dict[str, dict] = {
    "explainer": {
        "label": "Finance / business explainer", "gate_type": "explainer", "pack": "explainer",
        "audience": "Curious adults 18-44 who want to understand how companies make money",
        "region": "India + US",
        "regions": {"IN": "Use rupees (₹) first with a dollar comparison; Indian companies by their listed names.",
                    "US": "Use dollars first; mention SEC filings (10-K) as sources."},
        "beat_sheet": ["hook: number or contradiction", "problem: why the viewer cares", "myth: what people assume",
                       "numbers: where the money really goes", "twist: the part nobody prices in",
                       "running example: one concrete business or person", "actionable takeaway",
                       "callback to the hook + next video"],
        "hook_formulas": ["number_stakes", "contradiction", "hidden_answer", "cold_open", "villain_system",
                          "before_after", "insider_view", "challenge_guess"],
        "min_minutes": 8, "max_minutes": 12, "shot_interval": (4, 7), "sentence_max_words": 18,
        "loop_distance": (60, 180), "min_loops_first_60s": 2, "analogy_every_seconds": 120,
        "compliance": ["Not financial advice: say so once, near the start or the end, in plain words.",
                       "Every figure has a fact id; estimates are worded as estimates.",
                       "No guaranteed returns, no 'buy this' calls."],
        "ending_style": "callback to the hook, one-sentence takeaway, a specific comment question, next video",
        "needs_disclaimer": True, "number_first_hooks": True, "kids": False,
        "music_default": "neutral", "extra_banned": [],
    },
    "history": {
        "label": "History / story", "gate_type": "story", "pack": "history",
        "audience": "Curious learners 16-55 who like cinematic stories about the past",
        "region": "global",
        "beat_sheet": ["cold open in second person: you are there", "the world before: calm", "the first crack",
                       "escalation: dread builds slowly", "sudden reveal", "the cost: human scale",
                       "chapter-end cliffhanger (every chapter)", "aftermath", "what it still means today"],
        "hook_formulas": ["cold_open", "hidden_answer", "contradiction", "before_after", "challenge_guess",
                          "villain_system"],
        "min_minutes": 8, "max_minutes": 15, "shot_interval": (5, 8), "sentence_max_words": 20,
        "loop_distance": (30, 180), "min_loops_first_60s": 2, "analogy_every_seconds": 150,
        "compliance": ["Fact accuracy: dates and numbers carry fact ids; mark disputed points as disputed.",
                       "Demonetization-safe wording for graphic events: describe consequences, not gore; "
                       "no graphic violence detail, no slurs, no glorifying perpetrators.",
                       "Second-person POV is a device, never a claim that the viewer did something real."],
        "ending_style": "land the emotional beat, connect to today, tease the next story",
        "needs_disclaimer": False, "number_first_hooks": False, "kids": False,
        "music_default": "tense", "drop_before_twist": True,
        "extra_banned": ["little did they know", "and the rest is history", "history would never be the same"],
    },
    "kids": {
        "label": "Kids stories and songs", "gate_type": "kids", "pack": "kids",
        "audience": "Toddlers and preschoolers (1-6) watched with a parent", "region": "global",
        "beat_sheet": ["meet the character", "the goal", "a small obstacle", "try again (repeat)",
                       "call-and-response / counting moment", "happy resolution", "goodbye + wave"],
        "hook_formulas": ["cold_open", "hidden_answer", "challenge_guess"],
        "min_minutes": 3, "max_minutes": 8, "shot_interval": (3, 5), "sentence_max_words": 8,
        "wps": 2.0, "loop_distance": (20, 60), "min_loops_first_60s": 0, "analogy_every_seconds": 0,
        "min_words_per_sentence_variance": 0.0,
        "compliance": ["Child safety: no scary content, no violence, no peril beyond a tiny wobble.",
                       "No links, no asks for personal info, no product pushes, no real brands.",
                       "Made for Kids is always on. Tiny vocabulary (about 300 common words)."],
        "ending_style": "everyone is happy, repeat the song line, wave goodbye",
        "needs_disclaimer": False, "number_first_hooks": False, "kids": True,
        "music_default": "resolve", "drop_before_twist": False, "stinger_on_reveal": False,
        "voice": {"hook": {"rate": 4, "pitch": 4, "volume": 3}, "neutral": {"rate": -4, "pitch": 3, "volume": 2},
                  "reveal": {"rate": -2, "pitch": 5, "volume": 4}, "tense": {"rate": -4, "pitch": 2, "volume": 0},
                  "warm": {"rate": -6, "pitch": 3, "volume": 0}, "excited": {"rate": 4, "pitch": 6, "volume": 4},
                  "pauses": {"before_reveal": 0.0, "after_plant": 0.0, "chapter": 0.4}},
        "vocabulary_max_words": 12, "max_grade": 3, "extra_banned": ["die", "dead", "kill", "blood", "monster", "scary", "hate"],  # noqa: E501
        "flag_overrides": {"fact_ledger": False, "loop_ids": False, "hook_rotation": True,
                           "repetition_ledger": True},
    },
    "general": {
        "label": "General explainer", "gate_type": "explainer", "pack": "general",
        "audience": "General audience", "region": "global",
        "beat_sheet": ["hook", "why it matters", "how it works", "surprising detail", "example", "takeaway"],
        "hook_formulas": ["hidden_answer", "contradiction", "cold_open", "number_stakes", "challenge_guess"],
        "min_minutes": 6, "max_minutes": 12, "shot_interval": (4, 7), "sentence_max_words": 18,
        "loop_distance": (60, 180), "min_loops_first_60s": 2, "analogy_every_seconds": 120,
        "compliance": ["Cite a source for every figure; label estimates."],
        "ending_style": "callback, takeaway, a question, next video",
        "needs_disclaimer": False, "number_first_hooks": False, "kids": False,
        "music_default": "neutral", "extra_banned": [],
    },
}


def pack_name(channel_type: str | None) -> str:
    """Prompt-pack name for a channel type (unknown types fall back to 'general')."""
    return PACK_FOR_TYPE.get((channel_type or "business").strip().lower(), "general")


def get(pack: str, overrides: dict | None = None) -> dict:
    """Full profile for a pack: shared defaults < pack values < owner overrides. Includes merged `flags`."""
    base = copy.deepcopy(_SHARED)
    pk = copy.deepcopy(PACKS.get(pack, PACKS["general"]))
    base.update({k: v for k, v in pk.items() if k != "voice"})
    if "voice" in pk:
        base["voice"] = pk["voice"]
    flags = dict(DEFAULT_FLAGS)
    flags.update(pk.get("flag_overrides") or {})
    ov = copy.deepcopy(overrides or {})
    flags.update({k: bool(v) for k, v in (ov.pop("flags", None) or {}).items() if k in DEFAULT_FLAGS})
    for k, v in ov.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    base["flags"] = flags
    base["name"] = pack if pack in PACKS else "general"
    from studio.story.banned import BANNED_PHRASES
    base["banned_phrases"] = list(dict.fromkeys([*BANNED_PHRASES, *base.get("extra_banned", [])]))
    return base


def for_channel(root: Path) -> dict:
    """Profile of the active channel (its type's pack plus the channel's `story` overrides)."""
    from studio.growth import channels
    p = channels.get(root)
    return get(pack_name(p.get("type")), p.get("story") if isinstance(p.get("story"), dict) else None)


def enabled(profile: dict, flag: str) -> bool:
    """True if a feature flag is on for this profile."""
    return bool(profile.get("flags", {}).get(flag, False))


def length_bounds(profile: dict) -> tuple[float, float]:
    """(min, max) total narration seconds."""
    return profile["min_minutes"] * 60.0, profile["max_minutes"] * 60.0
