"""One place to load the bold display fonts, so text is the right size on every OS.

Pillow's built-in bitmap font ignores the requested size (about 10 px), which made speech bubbles and labels
unreadable on Windows and macOS. DejaVu ships with matplotlib, so it is always found; an own font dropped in
`assets/fonts` is used for the sans face first.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from studio.errors import StudioError


@lru_cache(maxsize=4)
def font_file(serif: bool = False) -> str:
    """Path of a bold TrueType font: DejaVu Serif Bold or DejaVu Sans Bold from matplotlib's bundled data."""
    from matplotlib import font_manager

    family = "DejaVu Serif" if serif else "DejaVu Sans"
    path = font_manager.findfont(font_manager.FontProperties(family=family, weight="bold"), fallback_to_default=True)
    if not Path(path).exists():
        raise StudioError("No usable font was found.", "matplotlib's bundled DejaVu fonts are missing.",
                          "Reinstall the requirements (pip install -r requirements.txt) or put a .ttf in assets/fonts.")
    return path


def load(size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    """A bold TrueType font at `size` pixels (never Pillow's tiny default bitmap font)."""
    return ImageFont.truetype(font_file(serif), size)
