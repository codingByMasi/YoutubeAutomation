"""SVG character sprites with blinking eyes and a talking mouth. Falls back to code-drawn shapes.

Each SVG has four groups: eyes-open, eyes-closed, mouth-closed, mouth-open. A variant is made by deleting the
two groups that are not wanted, then rasterised once per size with cairosvg and cached. Owners can replace any
character by putting `<name>.svg` in assets/kids/characters/ (same group ids).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image

BUILTIN = Path(__file__).parent / "cast"
GROUPS = ("eyes-open", "eyes-closed", "mouth-closed", "mouth-open")


def _drop(svg: str, group: str) -> str:
    """Remove `<g id="group">...</g>` (groups are flat in our SVGs)."""
    return re.sub(rf'<g id="{group}">.*?</g>', "", svg, flags=re.S)


def variant(svg: str, eyes_closed: bool, mouth_open: bool) -> str:
    """The SVG text with one eye state and one mouth state kept."""
    svg = _drop(svg, "eyes-open" if eyes_closed else "eyes-closed")
    return _drop(svg, "mouth-closed" if mouth_open else "mouth-open")


def missing_groups(svg: str) -> list[str]:
    """Group ids a character SVG must contain but does not."""
    return [g for g in GROUPS if f'id="{g}"' not in svg]


def available() -> bool:
    """True when cairosvg and the cairo library can be imported."""
    try:
        import cairosvg  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


class SpriteBank:
    """Loads and caches character sprites. `get` returns None when a character has no usable SVG."""

    def __init__(self, user_dir: Path | None = None) -> None:
        self.dirs = [d for d in (user_dir, BUILTIN) if d is not None]
        self._svg: dict[str, str | None] = {}
        self._png: dict[tuple, Image.Image] = {}
        self.enabled = available()

    def _source(self, name: str) -> str | None:
        if name not in self._svg:
            self._svg[name] = None
            for d in self.dirs:
                f = d / f"{name}.svg"
                if f.exists():
                    text = f.read_text(encoding="utf-8")
                    if not missing_groups(text):
                        self._svg[name] = text
                        break
        return self._svg[name]

    def get(self, name: str, px: int, eyes_closed: bool = False, mouth_open: bool = False) -> Image.Image | None:
        """RGBA sprite `px` pixels wide, or None to fall back to the code-drawn shape."""
        px = max(8, int(px) // 8 * 8)  # quantise so the cache stays small while sizes animate
        key = (name, px, eyes_closed, mouth_open)
        if key not in self._png:
            src = self._source(name) if self.enabled else None
            if src is None:
                return None
            import cairosvg

            png = cairosvg.svg2png(bytestring=variant(src, eyes_closed, mouth_open).encode(), output_width=px)
            self._png[key] = Image.open(io.BytesIO(png)).convert("RGBA")
        return self._png[key]


def blink(t: float, i: int) -> bool:
    """Eyes are shut for 0.15 s every ~3 s, offset per character so the group does not blink in unison."""
    return (t + i * 0.83) % 3.1 < 0.15


def talking(t: float, i: int, narration: float) -> bool:
    """Mouth flaps about five times a second while the narration plays."""
    return t < narration and int(t * 5 + i) % 2 == 0
