import json
import os
from pathlib import Path

from PIL import Image

from studio.models import Idea, Video
from studio.stages import thumbnail as th

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def test_noisy_image_is_compressed_under_2mb(tmp_path):
    noise = Image.frombytes("RGB", (1280, 720), os.urandom(1280 * 720 * 3))
    p = th.save_under_limit(noise, tmp_path / "t.jpg")
    assert p.stat().st_size < th.MAX_BYTES and th.validate_thumb(p) == []


def test_wrong_size_is_resized_and_validation_catches_bad_files(tmp_path):
    p = th.save_under_limit(Image.new("RGB", (640, 360), "red"), tmp_path / "small.jpg")
    assert Image.open(p).size == (1280, 720)
    bad = tmp_path / "bad.jpg"
    Image.new("RGB", (1000, 1000)).save(bad)
    assert "must be 1280x720" in th.validate_thumb(bad)[0]


def test_thumbnail_stage_makes_three_valid_variants(ctx):
    idea = Idea(seed="s", topic="t", status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage="built")
    ctx.session.add(v)
    ctx.session.commit()
    pkg = dict(SAMPLE, segments=[dict(s, real_seconds=8) for s in SAMPLE["segments"]])
    (ctx.settings.project_dir(v.id) / "script.json").write_text(json.dumps(pkg))
    made = th.run(ctx, v.id)
    assert len(made) == 3 and v.stage == "thumbnailed"
    for p in made:
        assert th.validate_thumb(p) == []
    assert len({p.read_bytes() for p in made}) == 3  # different layouts
    assert th.run(ctx, v.id) == []  # already done: no-op
    assert th.headline_number(pkg) == "$0.30"
