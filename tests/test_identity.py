import json

import pytest
from PIL import Image
from typer.testing import CliRunner

from studio.cli import app
from studio.errors import StudioError
from studio.growth import channels, identity, series
from studio.providers import brand
from studio.stages.script import build_prompt


def test_preset_applies_to_any_channel_and_reaches_prompts(root):
    cid = channels.add(root, "Money Stories")
    channels.update(root, cid, **identity.preset_fields("finance-stories"))
    p = channels.get(root, cid)
    assert p["mascot"]["name"] == "Penny" and len(p["playlists"]) == 3 and p["niche_statement"]
    prompt = build_prompt(root, "How Nvidia won")
    assert "Penny" in prompt and "Follow the money" in prompt and "Comeback Stories" in prompt
    other = channels.add(root, "Chef Talk", niche="Cooking science")
    assert channels.get(root, other)["mascot"] == {} and "Penny" not in channels.summary(channels.get(root, other))


def test_validation_errors_are_helpful(root):
    with pytest.raises(StudioError):
        channels.update(root, mascot={"name": "X", "kind": "dragon"})
    with pytest.raises(StudioError):
        channels.update(root, theme={"accent": "gold"})
    with pytest.raises(StudioError):
        channels.update(root, theme={"outro_style": "movie"})
    with pytest.raises(StudioError):
        channels.update(root, playlists=[{"name": "A"}, {"name": "a"}])
    got = channels.update(root, playlists=[{"name": "A", "topics": "one\ntwo"}])
    assert got["playlists"][0]["topics"] == ["one", "two"]


def test_theme_overrides_palette_and_brand_colours(root):
    from studio import production
    from studio.config import load_settings
    channels.update(root, **identity.preset_fields("finance-stories"))
    prod = production.resolve(load_settings(root))
    assert prod["palette"] == ("#0B1F3A", "#F5B700") and prod["sources"]["palette"] == "theme"
    with brand.use(prod["palette"], prod["theme"]):
        assert brand.ACCENT_2 == "#38BDF8" and brand.SERIES[1] == "#38BDF8"
    assert brand.ACCENT_2 == "#38BDF8" and brand.BG == "#0F172A"  # restored


@pytest.mark.parametrize("kind", identity.MASCOT_KINDS)
def test_mascot_draws_every_kind_and_mood(kind):
    for mood in identity.MOODS:
        im = identity.mascot_image({"kind": kind, "color": "#F5B700"}, 120, mood)
        assert im.size == (120, 120) and im.getchannel("A").getbbox()


def test_cards_and_thumbnail_badge(root):
    prof = channels.update(root, **identity.preset_fields("finance-stories"))
    card = identity.card_image(prof, "outro", "", "Next: How Costco makes money", None, (640, 360))
    assert card.size == (640, 360) and card.getpixel((5, 5)) == (11, 31, 58)
    base = Image.new("RGB", (1280, 720), "black")
    assert identity.paste_mascot(base, prof, 200).getbbox() and identity.paste_mascot(base, prof, 200) != base
    off = dict(prof, mascot=dict(prof["mascot"], on_thumbnail=False))
    assert identity.paste_mascot(base, off, 200) is base
    assert identity.paste_mascot(base, dict(prof, mascot={}), 200) is base


def test_playlists_become_series_and_pick_youtube_playlist(root):
    prof = channels.update(root, **identity.preset_fields("finance-stories"))
    assert identity.sync_playlists(root, prof) == ["Comeback Stories", "How Giants Make Money",
                                                   "Biggest Business Mistakes"]
    assert identity.sync_playlists(root, prof) == []  # idempotent
    assert identity.playlist_id_for(root, 7) is None
    prof = channels.update(root, playlists=[dict(prof["playlists"][0], youtube_id="PLabc")] + prof["playlists"][1:])
    identity.sync_playlists(root, prof)
    series.link_video(root, "Comeback Stories", 0, 7, "How Elon Musk went from near bankruptcy")
    assert identity.playlist_id_for(root, 7) == "PLabc"


def test_cli_identity_preset_and_preview(root, monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_HOME", str(root))
    args = ["channels", "identity", "--preset", "finance-stories", "--preview", str(tmp_path / "p")]
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 0, r.output
    assert "Penny" in r.output and "Comeback Stories" in r.output
    assert (tmp_path / "p" / "mascot.png").exists() and (tmp_path / "p" / "outro_card.png").exists()
    f = tmp_path / "id.json"
    f.write_text(json.dumps({"tagline": "Hello", "mascot": {"name": "Bo", "kind": "robot"}}))
    r = CliRunner().invoke(app, ["channels", "identity", "--file", str(f)])
    assert r.exit_code == 0 and "Bo (robot)" in r.output and "Hello" in r.output


def test_thumbnail_stage_shows_the_mascot(ctx):
    from pathlib import Path

    from studio.models import Idea, Video
    from studio.stages import thumbnail as th

    sample = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())

    def make(with_mascot: bool) -> bytes:
        channels.update(ctx.settings.root, mascot=identity.preset("finance-stories")["mascot"] if with_mascot else {})
        idea = Idea(seed="s", topic="t", status="approved")
        ctx.session.add(idea)
        ctx.session.flush()
        v = Video(idea_id=idea.id, stage="built")
        ctx.session.add(v)
        ctx.session.commit()
        pkg = dict(sample, segments=[dict(s, real_seconds=8) for s in sample["segments"]])
        (ctx.settings.project_dir(v.id) / "script.json").write_text(json.dumps(pkg))
        return th.run(ctx, v.id)[1].read_bytes()

    assert make(True) != make(False)


def test_identity_card_clip(ctx, tmp_path):
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from studio.stages import build
    from studio.util import ffmpeg as ff

    channels.update(ctx.settings.root, **identity.preset_fields("finance-stories"))
    pkg = {"titles": [{"text": "T", "is_pick": True}]}
    assert build._identity_card(ctx, "intro", pkg, 1, tmp_path) is None  # finance preset: cold open, no intro card
    clip = build._identity_card(ctx, "outro", pkg, 1, tmp_path)
    assert clip and 5.5 < ff.probe_duration(clip) < 6.5
