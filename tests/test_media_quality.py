"""Quality gate, captions, sound and the new ffmpeg builders."""

import random
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from studio.providers import captions, sound
from studio.providers.images import JUNK_NAME, relevance
from studio.stages import visuals
from studio.stages.build import sfx_events
from studio.util import ffmpeg as ff
from studio.util import media_check as mc

P = Path


def busy(path: Path, w=1920, h=1080, seed=1) -> Path:
    rng = random.Random(seed)
    im = Image.new("RGB", (w, h), (90, 120, 160))
    d = ImageDraw.Draw(im)
    for _ in range(80):
        x, y = rng.randint(0, w), rng.randint(0, h)
        d.rectangle([x, y, x + rng.randint(20, 300), y + rng.randint(20, 300)],
                    fill=tuple(rng.randint(0, 255) for _ in range(3)))
    im.save(path, quality=92)
    return path


def test_image_gate_accepts_good_and_rejects_bad(tmp_path):
    assert mc.check_image(busy(tmp_path / "ok.jpg")) == []
    assert any("below" in p for p in mc.check_image(busy(tmp_path / "small.jpg", 400, 250)))
    assert any("aspect" in p for p in mc.check_image(busy(tmp_path / "tall.jpg", 1100, 1500)))
    Image.new("RGB", (1920, 1080), "white").save(tmp_path / "flat.jpg")
    assert any("flat" in p for p in mc.check_image(tmp_path / "flat.jpg"))
    (tmp_path / "html.jpg").write_text("<html>429 Too Many Requests</html>")
    assert any("not a readable image" in p for p in mc.check_image(tmp_path / "html.jpg"))
    grad = Image.linear_gradient("L").rotate(90).resize((1920, 1080)).convert("RGB")  # smooth: no detail at all
    grad.save(tmp_path / "blur.png")
    assert any("blurry" in p for p in mc.check_image(tmp_path / "blur.png"))


def test_duplicate_detection(tmp_path):
    a = busy(tmp_path / "a.jpg", seed=1)
    a2 = tmp_path / "a2.jpg"
    Image.open(a).resize((1280, 720)).save(a2, quality=60)  # same picture, other size and compression
    b = busy(tmp_path / "b.jpg", seed=2)
    assert mc.similar(mc.dhash(a), mc.dhash(a2)) and not mc.similar(mc.dhash(a), mc.dhash(b))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_clip_gate(tmp_path):
    def clip(name, size, dur):
        out = tmp_path / name
        src = f"testsrc2=size={size}:rate=10:duration={dur}"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, "-pix_fmt", "yuv420p", str(out)],
                       check=True)
        return out
    assert mc.check_clip(clip("ok.mp4", "1280x720", 3)) == []
    assert any("below" in p for p in mc.check_clip(clip("small.mp4", "320x180", 3)))
    assert any("portrait" in p for p in mc.check_clip(clip("tall.mp4", "720x1280", 3)))
    (tmp_path / "junk.mp4").write_bytes(b"not a video")
    assert any("not a readable video" in p for p in mc.check_clip(tmp_path / "junk.mp4"))


def test_find_valid_skips_bad_and_duplicate_candidates(tmp_path):
    from studio.providers.footage import StockClip
    files = [tmp_path / "html.jpg", busy(tmp_path / "a.jpg", seed=1), busy(tmp_path / "a_again.jpg", seed=1),
             busy(tmp_path / "b.jpg", seed=2)]
    files[0].write_text("<html>")
    it = iter(files)

    class Prov:
        def find(self, kw, seen):
            f = next(it, None)
            return StockClip(f, "u", "a", "u", "CC0", "T") if f else None
    hashes, rejected = [], []
    got = [visuals.find_valid(Prov(), ["x"], set(), "image", hashes, rejected) for _ in range(2)]
    assert [g.path.name for g in got] == ["a.jpg", "b.jpg"]
    assert len(rejected) == 2 and "not a readable" in rejected[0] and "near-duplicate" in rejected[1]


def test_relevance_and_junk_filter():
    assert relevance("cruise ship deck", "ship, cruise, sea, deck") == 1.0
    assert relevance("cruise ship deck", "kitten, garden") == 0.0
    assert JUNK_NAME.search("File:Carnival logo.png") and JUNK_NAME.search("File:World map 1900.jpg")
    assert not JUNK_NAME.search("File:Cruise ship at sunset.jpg")


# ---------- captions ----------
def test_script_word_timing_and_phrases():
    words = captions.words_from_script([(0, 4), (4, 10)], ["Five dollars. Where does it go?", "Rent, mostly."])
    assert words[0][0] == 0 and words[-1][1] == pytest.approx(10)
    assert all(a[1] <= b[0] + 1e-6 for a, b in zip(words, words[1:]))
    for ph in captions.phrases(words):
        assert len(ph) <= 4 and len(" ".join(w[2] for w in ph)) <= 26


def test_ass_highlights_active_word_and_banners_chapters():
    words = captions.words_from_script([(0, 4), (4, 8)], ["It costs $5 today.", "Rent takes most."])
    ass = captions.to_ass(words, chapters=[(4.0, "Where it goes")])
    assert "[Events]" in ass and "Style: Banner" in ass and "WHERE IT GOES" in ass
    assert "&H0050E050&" in ass  # the figure gets the money colour
    assert ass.count("Dialogue: 0,") == len(words)
    clipped = captions.to_ass(words, window=(4, 8))
    assert "IT COSTS" not in clipped and "0:00:00.00" in clipped


# ---------- sound ----------
def test_generated_sound_files_exist_and_are_not_clipping(tmp_path):
    import wave

    import numpy as np
    files = sound.ensure_sound(tmp_path)
    assert set(files) == {"music", "silence", "whoosh", "pop", "hit"}
    for name, f in files.items():
        if name == "silence":
            continue
        with wave.open(str(f)) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
            assert w.getframerate() == 48000 and w.getnchannels() == 2 and len(data) > 1000
            assert 0.05 < np.abs(data).max() / 32767 <= 1.0, name


def test_sfx_events_and_mix_graph():
    segs = [{"beat": None}, {"beat": "reveal"}, {"beat": "question", "chart_data": {"type": "bar"}}]
    plans = [[(P("a.jpg"), 10)], [(P("b.jpg"), 10)], [(P("charts/c1.png"), 5), (P("charts/c2.png"), 5)]]
    ev = sfx_events(segs, plans)
    assert ("hit", 10) in ev and ("whoosh", 19.55) in ev and ("pop", 25) in ev
    cmd = ff.mix_cmd(P("v.mp4"), P("n.wav"), P("o.mp4"), P("m.wav"), -17,
                     sfx={"whoosh": P("w.wav"), "hit": P("h.wav"), "pop": P("p.wav")}, sfx_events=ev, total=30)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" in fc and "adelay=10000" in fc and "[sfx]" in fc and "afade=t=out:st=27.00" in fc
    assert cmd.count("-i") == 6  # video, voice, music, three effects


# ---------- ffmpeg builders ----------
def test_ken_burns_is_centred_and_varied():
    cmds = [" ".join(ff.image_cmd(P("i.jpg"), 4, P("o.mp4"), motion=m)) for m in range(5)]
    assert len(set(cmds)) == 5
    assert all("zoompan" in c and "iw/zoom" in c for c in cmds)  # anchored on the centre, not the top-left corner
    wide = " ".join(ff.image_cmd(P("i.jpg"), 4, P("o.mp4"), aspect=1.78))
    boxy = " ".join(ff.image_cmd(P("i.jpg"), 4, P("o.mp4"), aspect=1.3))
    assert "boxblur" not in wide and "boxblur" in boxy


def test_xfade_offsets_keep_total_length():
    cmd = ff.xfade_cmd([P("a"), P("b"), P("c")], [4, 5, 3], P("o"), fade=0.3)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "offset=4.000" in fc and "offset=9.000" in fc and fc.count("xfade") == 2
    with pytest.raises(ValueError):
        ff.xfade_cmd([P("a")], [4], P("o"))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_dissolved_segment_has_exact_length(tmp_path):
    parts, durs = [], [2.0, 2.5, 1.5]
    for i, d in enumerate(durs):
        img = busy(tmp_path / f"i{i}.jpg", seed=i)
        out = tmp_path / f"p{i}.mp4"
        extra = ff.XFADE_SECONDS if i < len(durs) - 1 else 0
        ff.run(ff.image_cmd(img, d + extra, out, motion=i, aspect=1.3 if i == 1 else 1.78), "render")
        parts.append(out)
    final = tmp_path / "seg.mp4"
    ff.run(ff.xfade_cmd(parts, durs, final), "xfade")
    assert ff.probe_duration(final) == pytest.approx(sum(durs), abs=0.15)


def test_stock_relevance_and_number_formatting():
    """Unrelated stock footage is skipped; currency units read as $5.03 trillion, not '5.03 trillion US$'."""
    from studio.providers.charts import fmt
    from studio.providers.footage import is_relevant
    assert is_relevant("nvidia graphics card", "gpu, graphics, card, computer")
    assert not is_relevant("nvidia chip", "playstation, console, game, controller")
    assert fmt(5.03, "trillion US$") == "$5.03 trillion"
    assert fmt(2.5, "billion USD") == "$2.5 billion"
    assert fmt(35, "%") == "35%"
