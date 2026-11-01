"""Channel types and the thresholds the quality gate uses for each. Retention rules can tighten these per channel."""

from __future__ import annotations

DIMENSIONS = ("script", "hook", "pacing", "visuals", "audio", "metadata")

# Every number here is a rule of thumb, not a YouTube rule; owners tune them per channel through feedback rules.
TYPES: dict[str, dict] = {
    "explainer": {
        "label": "Business / economics explainer", "hook_max_seconds": 15, "hook_first_sentence_words": 12,
        "beat_gap_max": 40, "sentence_max_words": 22, "card_share_max": 0.3, "min_minutes": 6,
        "min_open_loops": 2, "min_tags": 5, "lufs_target": -16.0, "lufs_tolerance": 2.5,
        "block_below": 55, "pass_at": 75, "needs_cta": True, "needs_sources": True,
        "weights": {"script": 1.0, "hook": 1.5, "pacing": 1.2, "visuals": 1.0, "audio": 0.8, "metadata": 0.8},
    },
    "story": {
        "label": "Narrative / documentary story", "hook_max_seconds": 20, "hook_first_sentence_words": 16,
        "beat_gap_max": 50, "sentence_max_words": 24, "card_share_max": 0.25, "min_minutes": 6,
        "min_open_loops": 3, "min_tags": 5, "lufs_target": -16.0, "lufs_tolerance": 2.5,
        "block_below": 55, "pass_at": 75, "needs_cta": True, "needs_sources": True,
        "weights": {"script": 1.2, "hook": 1.5, "pacing": 1.0, "visuals": 1.2, "audio": 1.0, "metadata": 0.6},
    },
    "kids": {
        "label": "Kids songs and learning", "hook_max_seconds": 8, "hook_first_sentence_words": 8,
        "beat_gap_max": 20, "sentence_max_words": 12, "card_share_max": 0.1, "min_minutes": 2,
        "min_open_loops": 0, "min_tags": 5, "lufs_target": -16.0, "lufs_tolerance": 2.0,
        "block_below": 60, "pass_at": 80, "needs_cta": False, "needs_sources": False,
        "weights": {"script": 0.6, "hook": 1.0, "pacing": 1.2, "visuals": 1.6, "audio": 1.6, "metadata": 0.8},
    },
}
DEFAULT_TYPE = "explainer"
# Keys that retention feedback may override per channel (see feedback.py).
TUNABLE = ("hook_max_seconds", "beat_gap_max", "sentence_max_words", "card_share_max", "min_minutes")


def channel_type(profile: dict) -> str:
    """The profile's channel_type if known, else a guess from its niche, else the default."""
    t = str(profile.get("channel_type") or "").strip().lower()
    if t in TYPES:
        return t
    niche = f"{profile.get('niche', '')} {profile.get('description', '')}".lower()
    if any(w in niche for w in ("kids", "nursery", "children", "toddler")):
        return "kids"
    if any(w in niche for w in ("story", "documentary", "true crime", "history")):
        return "story"
    return DEFAULT_TYPE


def thresholds(ctype: str, tuning: dict | None = None) -> dict:
    """Type thresholds with the channel's learned tuning laid over the tunable keys only."""
    base = dict(TYPES.get(ctype, TYPES[DEFAULT_TYPE]))
    for k, v in (tuning or {}).items():
        if k in TUNABLE and isinstance(v, (int, float)):
            base[k] = v
    return base
