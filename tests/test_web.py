"""Web helpers and a Streamlit smoke test (no network, no real keys)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from studio.errors import StudioError
from studio.models import Idea, Video
from studio.stages import research
from studio.web import service as svc

SAMPLE = Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json"


def _approved(ctx) -> tuple[Idea, Video]:
    idea = svc.add_manual_topic(ctx, "how airlines make money")
    return idea, research.approve(ctx, idea.id)


def test_apply_secrets_only_known_keys(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    applied = svc.apply_secrets({"PEXELS_API_KEY": "abc123", "EVIL": "x", "PIXABAY_API_KEY": ""})
    assert applied == ["PEXELS_API_KEY"] and os.environ["PEXELS_API_KEY"] == "abc123"
    assert "EVIL" not in os.environ
    monkeypatch.delenv("PEXELS_API_KEY")


def test_manual_topic_rejects_empty(make_ctx):
    with pytest.raises(StudioError):
        svc.add_manual_topic(make_ctx(), "  ")


def test_script_handoff_and_paste_flow(make_ctx):
    ctx = make_ctx()
    idea, video = _approved(ctx)
    from studio.stages import script

    res = svc.capture(script.run, ctx, idea.id)
    assert res.pending and not res.ok
    prompt = svc.read_prompt(ctx, video.id)
    assert prompt and "How to answer" not in prompt and "ONLY the JSON" in prompt

    bad = svc.submit_script(ctx, idea.id, video.id, "not json")
    assert not bad.ok and "valid JSON" in bad.error
    good = svc.submit_script(ctx, idea.id, video.id, SAMPLE.read_text(encoding="utf-8"))
    assert good.ok, good.error
    assert ctx.session.get(Video, video.id).stage == "scripted"
    assert svc.next_produce_stage(ctx.session.get(Video, video.id)) == "voice"


def test_review_gate_needs_typed_yes(make_ctx):
    ctx = make_ctx()
    assert ctx.confirm("anything") != "yes"
    wired = svc.make_ctx(ctx.settings.root, lambda _p: "no")
    assert wired.confirm("p") == "no"
    assert svc.make_ctx(ctx.settings.root).confirm("p") == ""


def test_zip_and_files(make_ctx):
    ctx = make_ctx()
    _, video = _approved(ctx)
    d = ctx.settings.project_dir(video.id)
    (d / "final.mp4").write_bytes(b"x")
    (d / "prompts").mkdir(exist_ok=True)
    (d / "prompts" / "script.prompt.md").write_text("secret-ish")
    import io
    import zipfile

    names = zipfile.ZipFile(io.BytesIO(svc.zip_outputs(ctx, video.id))).namelist()
    assert names == ["final.mp4"]


def test_app_renders_every_page(root, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("STUDIO_HOME", str(root))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert not at.exception
    for page in ["1. Topics", "2. Script", "3. Make the video", "4. Review and download", "Settings"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page
