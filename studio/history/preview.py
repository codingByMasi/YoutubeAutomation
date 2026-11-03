"""Preview sheet: one recurring character in every outfit, side by side (no GPU, needs cairosvg)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from studio.errors import StudioError
from studio.history import cast, wardrobe
from studio.history.render import INK, font

CELL, LABEL = 300, 52
COLS = 4


def sheet(char_id: str = "quill") -> Image.Image:
    """RGB contact sheet of `char_id` in the default outfit and every era, labelled with the era name."""
    if char_id not in cast.ROSTER:
        raise StudioError(f"No recurring character called {char_id!r}.", f"Known: {', '.join(cast.ROSTER)}.",
                          "Pick one of the ids above.")
    try:
        import cairosvg
    except (ImportError, OSError) as exc:
        raise StudioError("The wardrobe preview needs cairosvg.", str(exc), "Run `pip install cairosvg`.") from exc
    outfits = [(wardrobe.DEFAULT, "Default"), *((e, wardrobe.OUTFITS[e]["name"]) for e in wardrobe.ERAS)]
    rows = -(-len(outfits) // COLS)
    img = Image.new("RGB", (COLS * CELL, rows * (CELL + LABEL)), (250, 244, 230))
    d = ImageDraw.Draw(img)
    for i, (eid, label) in enumerate(outfits):
        png = cairosvg.svg2png(bytestring=cast.roster_svg(char_id, eid).encode(), output_width=CELL - 20)
        spr = Image.open(io.BytesIO(png)).convert("RGBA")
        x, y = (i % COLS) * CELL, (i // COLS) * (CELL + LABEL)
        img.paste(spr, (x + 10, y + 4), spr)
        d.text((x + CELL / 2, y + CELL + LABEL / 2 - 6), label, font=font(26, serif=False), fill=INK, anchor="mm")
    return img


def write_sheet(char_id: str, out: Path) -> Path:
    """Save `sheet(char_id)` as a PNG at `out` (parent folders are created)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet(char_id).save(out)
    return out
