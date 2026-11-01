"""Brand colours and fonts shared by charts, cards and thumbnails."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Defaults until SPEC section 9 brand colours are chosen.
BG = "#0F172A"
FG = "#F8FAFC"
MUTED = "#94A3B8"
ACCENT = "#F59E0B"
ACCENT_2 = "#38BDF8"
SERIES = [ACCENT, ACCENT_2, "#A3E635", "#F472B6", "#C084FC", "#FB923C"]


@contextmanager
def use(palette: tuple[str, str] | None) -> Iterator[None]:
    """Temporarily switch the background and accent colours (a channel's palette) for charts and thumbnails."""
    global BG, ACCENT
    old = (BG, ACCENT, SERIES[0])
    if palette:
        BG, ACCENT = palette
        SERIES[0] = ACCENT
    try:
        yield
    finally:
        BG, ACCENT, SERIES[0] = old


def font_path(assets_dir: Path | None = None, bold: bool = True) -> str:
    """First .ttf/.otf in assets/fonts, else matplotlib's bundled DejaVu Sans."""
    if assets_dir:
        fonts = sorted((assets_dir / "fonts").glob("*.[ot]tf"))
        if fonts:
            return str(fonts[0])
    from matplotlib import font_manager

    return font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans",
                                                             weight="bold" if bold else "normal"))
