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
def use(palette: tuple[str, str] | None, theme: dict | None = None) -> Iterator[None]:
    """Temporarily switch the colours (a channel's palette and optional theme) for charts and thumbnails.

    `theme` may hold bg, accent, accent2 and text (see identity.colors); it wins over `palette`."""
    global BG, ACCENT, ACCENT_2, FG
    old = (BG, ACCENT, ACCENT_2, FG, SERIES[0], SERIES[1])
    if palette:
        BG, ACCENT = palette
    if theme:
        BG, ACCENT, ACCENT_2, FG = theme["bg"], theme["accent"], theme["accent2"], theme["text"]
    SERIES[0], SERIES[1] = ACCENT, ACCENT_2
    try:
        yield
    finally:
        BG, ACCENT, ACCENT_2, FG, SERIES[0], SERIES[1] = old


def font_path(assets_dir: Path | None = None, bold: bool = True) -> str:
    """First .ttf/.otf in assets/fonts, else matplotlib's bundled DejaVu Sans."""
    if assets_dir:
        fonts = sorted((assets_dir / "fonts").glob("*.[ot]tf"))
        if fonts:
            return str(fonts[0])
    from matplotlib import font_manager

    return font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans",
                                                             weight="bold" if bold else "normal"))
