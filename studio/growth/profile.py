"""Channel profile: the owner's answers that shape every growth tool. Defaults are used until filled in."""

from __future__ import annotations

from pathlib import Path

from studio.growth import store

DEFAULTS: dict = {
    "name": "My Channel",
    "niche": "Business-model and economics explainers",
    "language": "English",
    "audience": "Curious adults 18-44 who want to understand how companies make money",
    "posts_per_week": 2,
    "voice": "en-US-GuyNeural",
    "brand_primary": "#0B1F3A",
    "brand_accent": "#F5B700",
    "existing_videos": 0,
    "subscribers": 0,
    "watch_hours": 0.0,
    "newsletter_url": "",
    "affiliate_note": "",
}


def load(root: Path) -> dict:
    """Saved profile merged over the defaults."""
    return {**DEFAULTS, **store.load(store.channel_file(root, "profile"), {})}


def save(root: Path, values: dict) -> dict:
    """Save known fields only; returns the merged profile."""
    clean = {k: values[k] for k in DEFAULTS if k in values}
    merged = {**load(root), **clean}
    store.save(store.channel_file(root, "profile"), merged)
    return merged


def summary(p: dict) -> str:
    """One paragraph for prompts."""
    return (f"Channel '{p['name']}': {p['niche']}. Language: {p['language']}. Audience: {p['audience']}. "
            f"Posts {p['posts_per_week']} long video(s) per week. Faceless narration with charts and diagrams.")
