"""Optional Manim templates (timeline, flow, number counter, chart reveal) used instead of static cards.

Manim is heavy, so this module only detects it: `render` returns None when Manim is missing (or a template is not
written yet) and the caller keeps the matplotlib chart. Nothing here is required.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

TEMPLATES = ("timeline", "flow", "counter", "chart_reveal")


def available() -> bool:
    return importlib.util.find_spec("manim") is not None


def render(kind: str, data: dict, out: Path) -> Path | None:
    """Render a Manim scene to `out`, or None to fall back to matplotlib. Templates plug in here."""
    if kind not in TEMPLATES or not available():
        return None
    return None  # adapter point: add Scene subclasses per template and render with the Manim CLI
