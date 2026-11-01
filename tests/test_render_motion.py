"""Renderer report, caption size, animated charts and the opening camera move."""

import shutil

import pytest

from studio import render_report
from studio.providers import chart_anim
from studio.providers.captions import CaptionStyle
from studio.util import ffmpeg as ff

BAR = {"type": "bar", "title": "T", "labels": ["A", "B"], "values": [3, 5], "unit": "$", "source_ids": ["s1"]}


def test_captions_are_modest():
    st = CaptionStyle()
    assert st.size <= round(1080 * 0.05) and st.margin_v < 100


def test_hook_move_is_bigger():
    normal = ff.motion_exprs("in", 100)[0]
    punch = ff.motion_exprs("in", 100, 2.0)[0]
    assert normal != punch and "0.2" in punch


def test_chart_anim_command_holds_the_finished_chart(tmp_path):
    cmd = " ".join(ff.chart_anim_cmd(tmp_path / "a.mp4", tmp_path / "s.png", 4.0, tmp_path / "o.mp4"))
    assert "concat=n=2" in cmd and "-loop 1" in cmd


def test_easing_ends_at_one():
    assert chart_anim.ease(0) == 0 and chart_anim.ease(1) == 1


def test_non_animated_charts_are_skipped(tmp_path):
    assert chart_anim.animate({"type": "pie", "values": [1]}, [tmp_path / "x_step1.png"], "", tmp_path) == {}


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_bar_chart_gets_an_animation(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_anim, "FRAMES", 4)
    png = tmp_path / "seg_001_step2.png"
    png.write_bytes(b"x")
    got = chart_anim.animate(BAR, [png], "src", tmp_path)
    assert got and (tmp_path / "seg_001_step2.anim.mp4").stat().st_size > 0


def test_preflight_explains_2d(ctx):
    rep = render_report.preflight(ctx.settings, 1, [{"narration": "x"}])
    assert rep["verdict"] == "2D" and rep["notes"]
