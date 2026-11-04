"""SVG to PNG with two engines, so characters draw on any PC.

cairosvg is tried first. On Windows it imports fine but fails to draw when the native Cairo library is missing,
so `resvg-py` (a self-contained wheel, no native install) is the fallback. `engine()` says which one works.
"""

from __future__ import annotations

from functools import lru_cache

_PROBE = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4"/></svg>'


def _cairo(svg: bytes, width: int) -> bytes:
    import cairosvg
    return cairosvg.svg2png(bytestring=svg, output_width=width)


def _resvg(svg: bytes, width: int) -> bytes:
    import resvg_py
    return bytes(resvg_py.svg_to_bytes(svg_string=svg.decode("utf-8"), width=width))


@lru_cache(maxsize=1)
def engine() -> str:
    """'cairosvg', 'resvg' or '' when neither can draw. Probed once per process by really drawing."""
    for name, fn in (("cairosvg", _cairo), ("resvg", _resvg)):
        try:
            if fn(_PROBE, 8)[:4] == b"\x89PNG":
                return name
        except Exception:  # noqa: BLE001 - ImportError, OSError (missing DLL) and render errors all mean "no"
            continue
    return ""


def available() -> bool:
    return bool(engine())


def svg_to_png(svg: bytes | str, width: int) -> bytes:
    """PNG bytes of `svg` scaled to `width` pixels. Raises RuntimeError when no engine works."""
    data = svg.encode("utf-8") if isinstance(svg, str) else svg
    eng = engine()
    if not eng:
        raise RuntimeError("No SVG renderer works: install resvg-py (pip install resvg-py).")
    return (_cairo if eng == "cairosvg" else _resvg)(data, int(width))
