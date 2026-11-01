"""The active channel's profile. Thin wrapper over `channels`, kept so growth tools keep one import."""

from __future__ import annotations

from pathlib import Path

from studio.growth import channels

DEFAULTS = channels.DEFAULTS
summary = channels.summary


def load(root: Path) -> dict:
    """The active channel's profile merged over the defaults."""
    return channels.get(root)


def save(root: Path, values: dict) -> dict:
    """Save known fields on the active channel; returns the merged profile."""
    return channels.update(root, **values)
