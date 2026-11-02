"""Pluggable stock footage providers. `make_footage` picks one from settings, or None for cards only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from studio.errors import ConfigError


@dataclass
class StockClip:
    """A downloaded clip plus the licence record stored with its asset."""

    path: Path
    page_url: str
    author: str
    author_url: str
    licence: str
    provider: str


class FootageProvider(Protocol):
    """Anything with find(): first unused clip for the first keyword that returns results."""

    def find(self, keywords: list[str], exclude: set[int] | None = None) -> StockClip | None: ...


STOP = {"a", "an", "the", "of", "in", "on", "at", "and", "or", "to", "for", "with", "by", "from", "view", "close", "up"}


def is_relevant(keyword: str, text: str) -> bool:
    """True when at least one meaningful word of `keyword` appears in the clip's tags/title/slug.

    Stops stock search from returning unrelated footage (a PS4 for "Nvidia", lavender for "survived").
    """
    words = [w for w in re.findall(r"[a-z0-9]+", keyword.lower()) if w not in STOP and len(w) > 2]
    hay = text.lower()
    return not words or any(w in hay or (w.endswith("s") and w[:-1] in hay) for w in words)


KEY_FOR = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}


def resolve_provider(settings) -> str:
    """Name of the provider to use: pexels, pixabay or none.

    auto picks Pexels if its key is set, else Pixabay if its key is set, else none.
    An explicit choice whose key is missing raises ConfigError.
    """
    keys = {"pexels": settings.pexels_api_key, "pixabay": settings.pixabay_api_key}
    choice = settings.footage_provider
    if choice == "auto":
        return next((n for n in ("pexels", "pixabay") if keys[n]), "none")
    if choice in keys and not keys[choice]:
        raise ConfigError(
            f"FOOTAGE_PROVIDER={choice} but {KEY_FOR[choice]} is empty.",
            f"The `visuals` command needs that key to fetch {choice.title()} clips.",
            f"Add {KEY_FOR[choice]}=... to .env, or set FOOTAGE_PROVIDER=none to use generated cards only.",
        )
    return choice


class ChainedFootage:
    """Tries each provider in order; a provider that errors is logged as an issue and skipped (cards are the end)."""

    def __init__(self, providers: list[tuple[str, FootageProvider]], root=None) -> None:
        self.providers, self.root = providers, root

    def find(self, keywords: list[str], exclude: set[int] | None = None) -> StockClip | None:
        from studio import health
        for name, prov in self.providers:
            try:
                clip = prov.find(keywords, exclude)
            except Exception as exc:  # noqa: BLE001 - try the other source
                if self.root is not None:
                    health.record(self.root, f"stock footage ({name})", exc)
                continue
            if clip:
                return clip
        return None


def make_footage(settings) -> tuple[str, FootageProvider | None]:
    """(provider name, instance). Instance is None when only generated cards will be used."""
    name = resolve_provider(settings)
    if settings.footage_provider == "auto" and settings.pexels_api_key and settings.pixabay_api_key:
        from studio.providers.pexels import Pexels
        from studio.providers.pixabay import Pixabay
        a = Pexels(settings.pexels_api_key, settings.assets_dir / "cache" / "pexels")
        b = Pixabay(settings.pixabay_api_key, settings.assets_dir / "cache" / "pixabay")
        return "pexels+pixabay", ChainedFootage([("Pexels", a), ("Pixabay", b)], settings.root)
    cache = settings.assets_dir / "cache" / name
    from studio.providers.guard import Guarded
    if name == "pexels":
        from studio.providers.pexels import Pexels
        return name, Guarded(Pexels(settings.pexels_api_key, cache), "Pexels", "PEXELS_API_KEY")
    if name == "pixabay":
        from studio.providers.pixabay import Pixabay
        return name, Guarded(Pixabay(settings.pixabay_api_key, cache), "Pixabay", "PIXABAY_API_KEY")
    return "none", None
