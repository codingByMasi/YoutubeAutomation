"""On-demand photo scenes: validation, prompt packs, the scene clip, and the fallback to the drawn scene."""

from __future__ import annotations

import shutil

import pytest
from PIL import Image

from studio.errors import StudioError
from studio.scenes import photo as scene
from studio.story import photo, profile, prompts


def seg(**kw):
    return {"narration": "x", **kw}


def test_no_photo_key_means_no_photo_and_no_problems():
    assert photo.request(seg()) is None
    assert photo.photo_problems([seg(), seg(), seg()]) == []


def test_request_fills_defaults():
    r = photo.request(seg(photo={"subject": " Carthage ruins "}))
    assert r == {"subject": "Carthage ruins", "caption": "", "layout": "inset"}
    assert photo.request(seg(photo={"subject": ""})) is None


def test_photo_problems():
    segs = [seg(photo={"subject": "x"}), seg(photo={"subject": "y"}), seg(photo={"subject": "z", "layout": "wide"}),
            seg(photo={"subject": "w", "caption": "one two three four five six seven eight nine"}), seg(photo={})]
    text = " | ".join(photo.photo_problems(segs))
    for needle in ("no photo in the hook", "two segments in a row", "'wide'", "longer than 8", "needs a `subject`",
                   "4 photo scenes"):
        assert needle in text


@pytest.mark.parametrize("pack", ["history", "kids", "general"])
def test_every_script_prompt_carries_the_photo_rule(pack):
    prof = profile.get(pack)
    rule = photo.prompt_rule(pack)
    assert "OPTIONAL and rare" in rule and "At most 3" in rule
    assert "OPTIONAL and rare" in prompts.compose("script", prof)


def test_photo_scene_draws_both_layouts_and_rejects_bad_file(tmp_path):
    pic = tmp_path / "p.jpg"
    Image.new("RGB", (1600, 900), (40, 120, 200)).save(pic)
    for layout in ("full", "inset"):
        assert scene.compose(pic, "A caption", layout).size == (round(1280 * 1.06), round(720 * 1.06))
    (tmp_path / "bad.jpg").write_bytes(b"nope")
    with pytest.raises(StudioError):
        scene.compose(tmp_path / "bad.jpg")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")
def test_photo_clip_is_made_once_and_changes_with_the_caption(tmp_path):
    pic = tmp_path / "p.jpg"
    Image.new("RGB", (1600, 900), (40, 120, 200)).save(pic)
    out = tmp_path / "s.mp4"
    scene.render_photo_scene(pic, out, 1.0, "Cap", "inset")
    assert out.stat().st_size > 1000
    first = out.stat().st_mtime_ns
    scene.render_photo_scene(pic, out, 1.0, "Cap", "inset")
    assert out.stat().st_mtime_ns == first
    scene.render_photo_scene(pic, out, 1.0, "Other", "inset")
    assert out.stat().st_mtime_ns != first


# ---- the visuals stage: a photo scene only where the script asks, drawn scene if the photo cannot be had
def _video_with_photo_ask(ctx):
    from studio.stages import script as sc
    from studio.stages import voice
    from tests.test_voice_visuals import FakeTTS, scripted_video
    v = scripted_video(ctx)
    voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 4.0)
    pkg = sc.load_package(ctx, v.id)
    pkg["segments"][1]["photo"] = {"subject": "Carthage ruins", "caption": "Carthage today", "layout": "inset"}
    sc.write_package(ctx, v.id, pkg)
    return v


class _Photos:
    def __init__(self, tmp, fail=False):
        self.tmp, self.fail, self.asked = tmp, fail, []

    def find(self, keywords, exclude):
        from studio.providers.footage import StockClip
        self.asked.append(list(keywords))
        if self.fail and keywords[0] == "Carthage ruins":
            raise StudioError("Pixabay rejected the key.", "401", "Fix PIXABAY_API_KEY.")
        p = self.tmp / f"photo{len(self.asked)}.jpg"
        Image.new("RGB", (1600, 900), (90, 60, 30)).save(p)
        return StockClip(p, "https://pixabay.com/photos/1", "Ann", "https://pixabay.com/users/ann-1/",
                         "Pixabay Content License", "Pixabay")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")
def test_visuals_makes_a_photo_scene_only_for_the_asked_segment(ctx, tmp_path):
    from studio.models import Asset
    from studio.stages import script as sc
    from studio.stages import visuals
    v = _video_with_photo_ask(ctx)
    photos = _Photos(tmp_path)
    visuals.run(ctx, v.id, stock=None, images=photos)
    segs = sc.load_package(ctx, v.id)["segments"]
    assert segs[1]["visual"]["scene"]["mode"] == "photo" and segs[1]["visual"]["scene_clip"].endswith(".mp4")
    assert any(a[0] == "Carthage ruins" for a in photos.asked)  # the script's subject is searched first
    assert all(s["visual"].get("scene", {}).get("mode") != "photo" for i, s in enumerate(segs) if i != 1)
    img = [a for a in ctx.session.query(Asset).filter_by(video_id=v.id) if a.kind == "image"]
    assert img and all(a.licence == "Pixabay Content License" and a.attribution_url for a in img)


def test_visuals_without_a_photo_ask_never_calls_the_photo_search_for_a_backdrop(ctx, tmp_path):
    from studio.stages import visuals, voice
    from tests.test_voice_visuals import FakeTTS, scripted_video
    v = scripted_video(ctx)
    voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 4.0)
    photos = _Photos(tmp_path)
    visuals.run(ctx, v.id, stock=None, images=photos)  # normal shots only, no photo scene anywhere
    from studio.stages import script as sc
    assert all(s["visual"].get("scene", {}).get("mode") != "photo" for s in sc.load_package(ctx, v.id)["segments"])


def test_failed_photo_falls_back_to_the_drawn_scene(ctx, tmp_path):
    from studio.stages import script as sc
    from studio.stages import visuals
    v = _video_with_photo_ask(ctx)
    visuals.run(ctx, v.id, stock=None, images=_Photos(tmp_path, fail=True))
    seg = sc.load_package(ctx, v.id)["segments"][1]
    assert seg["visual"].get("scene", {}).get("mode") != "photo"  # ordinary shots instead, build goes on


@pytest.fixture(autouse=True)
def fake_media_gate(monkeypatch):
    """Plain-colour test pictures would fail the real media gate (covered in test_media_quality.py)."""
    from studio.stages import visuals
    monkeypatch.setattr(visuals, "check_media", lambda path, kind: [])
    monkeypatch.setattr(visuals, "media_hash", lambda path, kind: None)
