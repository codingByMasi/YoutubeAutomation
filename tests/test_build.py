import json
import shutil
from pathlib import Path

import pytest

from studio.providers.whisper import _chunks, script_cues, to_srt, ts
from studio.stages.build import licence_for, normalize_cmd
from studio.stages.timing import pick_short_windows, plan_segment, shots_needed, split_segment
from studio.util import ffmpeg as ff

P = Path


def test_split_segment_gives_chart_most_of_the_time():
    assert split_segment(30, False) == (30, 0)
    assert split_segment(5, True) == (0, 5)
    bg, chart = split_segment(30, True)
    assert bg == 5 and chart == 25


def test_shots_keep_each_under_six_seconds():
    assert shots_needed(0) == 0 and shots_needed(5) == 1 and shots_needed(13) == 3 and shots_needed(100) == 4


def test_plan_fills_duration_exactly_and_changes_picture_often():
    plan = plan_segment(31.7, [P("a.mp4"), P("b.mp4")], [P("c1.png"), P("c2.png"), P("c3.png")])
    assert sum(s for _, s in plan) == pytest.approx(31.7)
    assert [p.name for p, _ in plan] == ["a.mp4", "c1.png", "c2.png", "c3.png"]
    plan = plan_segment(20, [P("a.mp4"), P("b.mp4")], [])
    assert [p.name for p, _ in plan] == ["a.mp4", "b.mp4", "a.mp4", "b.mp4"]
    assert all(s <= 6 for _, s in plan) and sum(s for _, s in plan) == pytest.approx(20)
    assert plan_segment(10, [], [P("c.png")]) == [(P("c.png"), 10)]


def test_short_windows_are_non_overlapping_and_sized():
    segs = [{"beat": b, "chart_data": c} for b, c in
            [("question", None), (None, None), ("reveal", {"x": 1}), (None, None), ("example", {"x": 1}),
             (None, None), ("reveal", None), (None, None)]]
    spans = [(i * 15.0, (i + 1) * 15.0) for i in range(len(segs))]
    wins = pick_short_windows(spans, segs, 3)
    assert 2 <= len(wins) <= 3
    for a, b in wins:
        length = spans[b][1] - spans[a][0]
        assert 15 <= length <= 58 and b < len(segs) - 1  # never the CTA segment
    flat = [k for a, b in wins for k in range(a, b + 1)]
    assert len(flat) == len(set(flat))


def test_caption_chunks_and_timing():
    assert all(len(c) <= 42 and len(c.split()) <= 8 for c in _chunks("word " * 40))
    cues = script_cues([(0, 4), (4, 10)], ["one two three four", "five six"])
    assert cues[0][0] == 0 and cues[-1][1] == 10
    srt = to_srt(cues, offset=3.0)
    assert srt.startswith("1\n00:00:03,000 --> ") and ts(3661.5) == "01:01:01,500"
    win = to_srt(cues, window=(4, 10))
    assert win.startswith("1\n00:00:00,000 --> 00:00:06,000\nfive six")


def test_ffmpeg_command_construction(tmp_path):
    cmd = ff.clip_cmd(P("in.mp4"), 4.5, P("out.mp4"))
    assert cmd[:4] == ["ffmpeg", "-y", "-stream_loop", "-1"] and "4.500" in cmd and "-an" in cmd
    assert any("scale=1920:1080" in c for c in cmd)
    mix = ff.mix_cmd(P("v.mp4"), P("n.wav"), P("o.mp4"), P("m.mp3"), -20.0, P("s.srt"))
    fc = mix[mix.index("-filter_complex") + 1]
    assert "volume=-20.0dB" in fc and "amix" in fc
    assert any(c.startswith("subtitles=") for c in mix) and "-shortest" in mix
    nomusic = ff.mix_cmd(P("v.mp4"), P("n.wav"), P("o.mp4"), None)
    assert "-filter_complex" not in nomusic and "1:a" in nomusic
    vert = ff.vertical_cmd(P("c.mp4"), 10, 30, P("s.mp4"), None)
    assert "1080:1920" in vert[vert.index("-filter_complex") + 1]
    assert "anullsrc" in " ".join(normalize_cmd(P("i.mp4"), P("o.mp4"), with_audio=False))


def test_music_ducked_at_least_15db():
    from studio.stages.build import MUSIC_DB
    assert MUSIC_DB <= -15


def test_licence_sidecar(tmp_path):
    song = tmp_path / "song.mp3"
    song.write_bytes(b"x")
    assert licence_for(song) == "unknown"
    (tmp_path / "song.mp3.licence.txt").write_text("YouTube Audio Library, monetization allowed\n")
    assert licence_for(song).startswith("YouTube Audio Library")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_missing_ffmpeg_message(monkeypatch):
    from studio.errors import StudioError
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(StudioError) as e:
        ff.ensure_ffmpeg()
    assert "install" in str(e.value).lower()
