import io

from PIL import Image

from studio.util import svg

RED = '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#f00"/></svg>'


def test_an_engine_draws_here():
    svg.engine.cache_clear()
    assert svg.available()


def test_svg_to_png_returns_requested_width():
    img = Image.open(io.BytesIO(svg.svg_to_png(RED, 32)))
    assert img.size[0] == 32 and img.convert("RGBA").getpixel((2, 2))[:3] == (255, 0, 0)


def test_falls_back_to_resvg_when_cairo_cannot_draw(monkeypatch):
    def broken(_svg, _w):
        raise OSError("no library called libcairo-2 was found")
    monkeypatch.setattr(svg, "_cairo", broken)
    svg.engine.cache_clear()
    try:
        assert svg.engine() == "resvg"
        assert svg.svg_to_png(RED.encode(), 16)[:4] == b"\x89PNG"
    finally:
        svg.engine.cache_clear()


def test_no_engine_raises_a_clear_error(monkeypatch):
    def broken(_svg, _w):
        raise OSError("nope")
    monkeypatch.setattr(svg, "_cairo", broken)
    monkeypatch.setattr(svg, "_resvg", broken)
    svg.engine.cache_clear()
    try:
        import pytest
        with pytest.raises(RuntimeError, match="resvg-py"):
            svg.svg_to_png(RED, 8)
    finally:
        svg.engine.cache_clear()
