import json
import shutil
from pathlib import Path

import pytest

from studio.models import Asset, Idea, Segment, Video
from studio.providers.pexels import StockClip, pick_file
from studio.stages import script as sc
from studio.stages import visuals, voice

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def scripted_video(ctx):
    idea = Idea(seed="coffee", topic=SAMPLE["topic"], status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage="approved")
    ctx.session.add(v)
    ctx.session.commit()
    (ctx.settings.project_dir(v.id) / "prompts" / "script.response.json").parent.mkdir(exist_ok=True)
    (ctx.settings.project_dir(v.id) / "prompts" / "script.response.json").write_text(json.dumps(SAMPLE))
    sc.run(ctx, idea.id)
    return v


class FakeTTS:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def synth(self, text, out):
        self.calls += 1
        out.write_bytes(b"ID3fake")
        return out


def test_real_durations_replace_estimates(ctx):
    v = scripted_video(ctx)
    tts = FakeTTS()
    voice.run(ctx, v.id, tts=tts, measure=lambda p: 9.5)
    rows = ctx.session.query(Segment).filter_by(video_id=v.id).all()
    assert all(r.real_seconds == 9.5 for r in rows) and all(r.est_seconds == 8 for r in rows)
    pkg = sc.load_package(ctx, v.id)
    assert [s["real_seconds"] for s in pkg["segments"]] == [9.5] * 6
    assert sc.timeline(pkg["segments"])[-1][1] == pytest.approx(57.0)
    assert v.stage == "voiced" and tts.calls == 6


def test_voice_is_idempotent(ctx):
    v = scripted_video(ctx)
    tts = FakeTTS()
    voice.run(ctx, v.id, tts=tts, measure=lambda p: 9.5)
    voice.run(ctx, v.id, tts=tts, measure=lambda p: 1.0)
    assert tts.calls == 6
    assert ctx.session.query(Segment).filter_by(video_id=v.id).first().real_seconds == 9.5


def test_voice_refuses_before_script(ctx):
    from studio.errors import StageError
    idea = Idea(seed="x", topic="x", status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage="approved")
    ctx.session.add(v)
    ctx.session.commit()
    with pytest.raises(StageError):
        voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 1)


class FakeStock:
    def __init__(self, tmp: Path, hits: set[int]):
        self.tmp, self.hits, self.n = tmp, hits, 0

    def find(self, keywords, exclude):
        self.n += 1
        if self.n not in self.hits:
            return None
        p = self.tmp / f"clip{self.n}.mp4"
        p.write_bytes(b"x")
        return StockClip(p, f"https://pexels.com/video/{self.n}", "Ann", "https://pexels.com/@ann")


def test_visuals_fallback_cards_and_licences(ctx, tmp_path):
    v = scripted_video(ctx)
    voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 8.0)
    visuals.run(ctx, v.id, stock=FakeStock(tmp_path, hits={1, 3}))
    assets = ctx.session.query(Asset).filter_by(video_id=v.id).all()
    kinds = [a.kind for a in assets]
    assert kinds.count("clip") == 2 and kinds.count("card") == 4 and kinds.count("chart") >= 3
    assert all(a.licence and a.licence != "unknown" for a in assets)
    clip = next(a for a in assets if a.kind == "clip")
    assert "Pexels" in clip.licence and clip.attribution_url.startswith("https://pexels.com/video/")
    pkg = sc.load_package(ctx, v.id)
    assert pkg["segments"][1]["visual"]["kind"] == "card"
    assert len(pkg["segments"][2]["visual"]["chart_frames"]) == 5  # bar chart revealed step by step
    assert all(Path(p).exists() for p in pkg["segments"][2]["visual"]["chart_frames"])
    assert v.stage == "visuals_ready"


def test_visuals_require_pexels_key(ctx):
    from studio.errors import ConfigError
    v = scripted_video(ctx)
    voice.run(ctx, v.id, tts=FakeTTS(), measure=lambda p: 8.0)
    with pytest.raises(ConfigError) as e:
        visuals.run(ctx, v.id)
    assert "PEXELS_API_KEY" in str(e.value)


def test_pexels_picks_full_hd_landscape_mp4():
    video = {"video_files": [
        {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "4k"},
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "hd"},
        {"file_type": "video/mp4", "width": 1280, "height": 720, "link": "720"},
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "portrait"},
    ]}
    assert pick_file(video)["link"] == "hd"


def test_pexels_search_is_cached(tmp_path):
    from studio.providers.pexels import Pexels

    calls = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.body

    def opener(req, timeout):
        calls.append(req.full_url)
        assert req.headers["Authorization"] == "KEY"
        return Resp(json.dumps({"videos": [{"id": 7}]}).encode())

    px = Pexels("KEY", tmp_path, opener=opener)
    assert px.search("coffee") == [{"id": 7}] and px.search("coffee") == [{"id": 7}]
    assert len(calls) == 1 and "api.pexels.com/v1/videos/search" in calls[0]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_silent_tts_produces_measurable_audio(tmp_path):
    from studio.providers.tts import SilentTTS
    from studio.util.ffmpeg import probe_duration
    p = SilentTTS().synth("one two three four five", tmp_path / "a.mp3")
    assert probe_duration(p) == pytest.approx(2.0, abs=0.2)
