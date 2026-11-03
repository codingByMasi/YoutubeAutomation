"""Fonts are real sized TrueType fonts, build records the real output, and the gate flags a non-1080p file."""

from studio.quality.gate import check_output
from studio.util import fonts


def test_fonts_are_truetype_and_scale():
    small, big = fonts.load(20), fonts.load(80, serif=True)
    assert small.getbbox("Hello")[3] < big.getbbox("Hello")[3]
    assert big.getbbox("Hello")[3] > 40  # Pillow's bitmap default would stay near 10 px


def test_no_module_uses_the_bitmap_default_font():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "studio"
    bad = [str(p) for p in root.rglob("*.py") if "load_default" in p.read_text(encoding="utf-8")
           and p.name != "fonts.py"]
    assert not bad, f"use studio.util.fonts instead of ImageFont.load_default: {bad}"


def test_gate_flags_draft_and_small_output():
    ok = {"build": {"video": {"width": 1920, "height": 1080, "fps": 30.0, "kbps": 2500}, "draft": False}}
    assert check_output(ok) == []
    small = {"build": {"video": {"width": 854, "height": 480, "fps": 24.0, "kbps": 600}, "draft": False}}
    assert any("1080p" in i["text"] for i in check_output(small))
    draft = {"build": {"video": {"width": 1280, "height": 720, "fps": 24.0, "kbps": 700}, "draft": True}}
    assert any("DRAFT" in i["text"] for i in check_output(draft))
    assert check_output({}) == []
