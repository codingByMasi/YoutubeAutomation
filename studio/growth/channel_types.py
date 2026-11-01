"""Channel types: each type picks a pipeline mode, prompt guidance, topic seeds and analytics hints.

A type only changes defaults and guidance; the owner can still edit every profile field.
"""

from __future__ import annotations

from studio.errors import StudioError

DEFAULT_TYPE = "business"

# Production settings the owner can pick per channel and per video ("" = use the type's default).
CHOICES: dict[str, tuple[str, ...]] = {
    "renderer": ("", "2d", "blender"),  # kids scenes and the narrated 3D title card
    "music": ("", "generated", "none"),  # generated royalty-free bed (or your own track in assets/music), or none
    "music_mood": ("", "minor", "major"),
    "tts_provider": ("", "edge", "eleven", "silent"),
}

TYPES: dict[str, dict] = {
    "business": {
        "label": "Business / economics explainer",
        "mode": "narrated", "made_for_kids": False,
        "niche": "Business-model and economics explainers",
        "audience": "Curious adults 18-44 who want to understand how companies make money",
        "guidance": "Narrated explainer with charts and diagrams. Every figure needs a public source.",
        "seeds": ["how it makes money", "the economics of", "why it failed", "unit economics of"],
        "music_mood": "minor", "palette": None,
        "analytics_hint": "Watch average view duration and retention; long explainers win on depth.",
    },
    "history": {
        "label": "History / education",
        "mode": "narrated", "made_for_kids": False,
        "niche": "History and education explainers",
        "audience": "Curious learners 16-55 who enjoy clear stories about the past and how things work",
        "guidance": "Narrated story with maps, timelines and archive-style images. Cite primary or reputable "
                    "sources for dates and claims; mark disputed points as disputed.",
        "seeds": ["the rise and fall of", "what really happened", "how it worked", "history of"],
        "music_mood": "minor", "palette": ("#2B1B12", "#E0A458"),
        "analytics_hint": "Evergreen topics grow slowly; compare views after 28+ days, not the first week.",
    },
    "kids": {
        "label": "Kids (nursery rhymes and learning songs)",
        "mode": "kids", "made_for_kids": True,
        "niche": "Original nursery rhymes and learning songs for toddlers",
        "audience": "Toddlers and preschoolers (ages 1-5) watched with a parent",
        "guidance": "Original songs and characters only, simple words, bright visuals. Uses Kids mode. "
                    "Every upload must be set to Made for Kids.",
        "seeds": ["counting song", "colors song", "animal sounds", "bedtime lullaby", "alphabet song"],
        "music_mood": "major", "palette": ("#1D4ED8", "#FACC15"),
        "analytics_hint": "Made for Kids videos have no comments and limited reports; expect fewer details.",
    },
    "general": {
        "label": "General",
        "mode": "narrated", "made_for_kids": False,
        "niche": "General explainers",
        "audience": "General audience",
        "guidance": "Narrated explainer. Be accurate, original and cite sources for facts.",
        "seeds": ["explained", "how it works", "why does"],
        "music_mood": "minor", "palette": None,
        "analytics_hint": "Compare views per day across videos of the same length.",
    },
}


def normalize(type_id: str | None) -> str:
    """Return a valid type id (blank means the default) or raise a helpful error."""
    t = (type_id or DEFAULT_TYPE).strip().lower()
    aliases = {"economics": "business", "education": "history", "edu": "history", "children": "kids"}
    t = aliases.get(t, t)
    if t not in TYPES:
        raise StudioError(f"Unknown channel type '{type_id}'.", f"Known types: {', '.join(TYPES)}.",
                          "Pick one of them, e.g. `--type kids`.")
    return t


def info(type_id: str | None) -> dict:
    """Definition of a channel type."""
    return TYPES[normalize(type_id)]
