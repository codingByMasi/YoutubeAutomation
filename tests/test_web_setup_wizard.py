"""Setup page helpers, per-channel sign-in, wizard steps, and Streamlit smoke tests for the new pages."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from studio.config import Settings
from studio.errors import StudioError
from studio.growth import channels
from studio.manage import doctor
from studio.models import Video
from studio.stages import research
from studio.web import service as svc
from studio.web import setup_service as setup
from studio.web import wizard_service as wiz

REPO = Path(__file__).parent.parent
CLIENT = json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}).encode()


class FakeCreds:
    valid = True

    def to_json(self):
        return json.dumps({"token": "t"})


@pytest.fixture
def envsafe(monkeypatch):
    """Register env keys with monkeypatch so values written by save_env are rolled back after the test."""
    for k in setup.ENV_KEYS:
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k)
    return monkeypatch


# ---------- per-channel sign-in ----------
def test_token_path_is_per_channel(root):
    assert Settings(root=root).token_path == root / "token.json"  # default channel keeps the legacy file
    assert Settings(root=root, channel_key="kids-1").token_path == root / "tokens" / "kids-1.json"


def test_sign_in_writes_token_for_active_channel(make_ctx, root):
    channels.add(root, "Second")
    ctx = make_ctx(channel_key=channels.active_id(root))
    ctx.settings.client_secret.write_bytes(CLIENT)
    res = setup.sign_in(ctx, run_flow=lambda s: FakeCreds(), services=lambda cid: None)
    assert res.ok and (root / "tokens" / "second.json").exists() and not (root / "token.json").exists()
    assert setup.signed_in(ctx.settings) and setup.signed_in_for(root, "second")
    assert not setup.signed_in_for(root, "default")
    assert setup.sign_out(ctx.settings) and not setup.signed_in(ctx.settings)


def test_sign_in_without_client_file_explains(ctx):
    res = setup.sign_in(ctx)
    assert not res.ok and "client_secret.json" in res.error


def test_load_settings_follows_active_channel(root, monkeypatch):
    from studio.config import load_settings

    monkeypatch.delenv("STUDIO_HOME", raising=False)
    cid = channels.add(root, "Money Maps")
    assert load_settings(root).channel_key == cid
    channels.switch(root, "default")
    assert load_settings(root).token_path == root / "token.json"


# ---------- saving keys and files ----------
def test_save_env_merges_and_limits_names(root, envsafe):
    (root / ".env").write_text("# keep\nPIXABAY_API_KEY=old\nOTHER=1\n")
    saved = setup.save_env(root, {"PIXABAY_API_KEY": " new ", "EVIL": "x", "TTS_VOICE": "en-GB-RyanNeural"})
    assert saved == ["PIXABAY_API_KEY", "TTS_VOICE"]
    text = (root / ".env").read_text()
    assert "PIXABAY_API_KEY=new" in text and "OTHER=1" in text and "# keep" in text and "EVIL" not in text
    assert os.environ["TTS_VOICE"] == "en-GB-RyanNeural"


@pytest.mark.parametrize("bad", [{"TTS_PROVIDER": "bogus"}, {"FOOTAGE_PROVIDER": "x"}, {"RENDERER": "x"},
                                 {"PIXABAY_API_KEY": "a\nb"}])
def test_save_env_rejects_bad_values(root, bad):
    with pytest.raises(StudioError):
        setup.save_env(root, bad)
    assert not (root / ".env").exists()


def test_save_client_secret_validates(ctx):
    path = setup.save_client_secret(ctx.settings, CLIENT)
    assert path.exists()
    with pytest.raises(StudioError, match="Desktop-app"):
        setup.save_client_secret(ctx.settings, json.dumps({"web": {}}).encode())
    with pytest.raises(StudioError, match="not valid JSON"):
        setup.save_client_secret(ctx.settings, b"nope")


# ---------- checklist ----------
def test_checks_put_failures_first_and_have_actions(ctx, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _n: None)
    cs = setup.checks(ctx.settings)
    assert cs[0].level == doctor.FAIL
    assert {c.action for c in cs if c.level != doctor.OK} >= {"ffmpeg", "client_secret", "channel_id"}
    blocking = setup.blocking(ctx.settings)
    assert blocking and all(c.action not in ("client_secret", "channel_id", "signin") for c in blocking)
    assert setup.section_level(cs, "ffmpeg") == doctor.FAIL and setup.section_level(cs, "nothing") == doctor.OK


def test_every_setup_action_has_guided_steps():
    from studio.web.setup_ui import SECTIONS

    assert all(a in setup.HOWTO for a, _ in SECTIONS)


def test_renderer_info_without_blender(ctx):
    info = setup.renderer_info(ctx.settings)
    assert info["blender_ok"] is False and "Blender" in info["note"]


# ---------- wizard ----------
def test_wizard_step_for_each_stage():
    steps = {"approved": "script", "scripted": "make", "voiced": "make", "visuals_ready": "make", "built": "make",
             "thumbnailed": "review", "reviewed": "publish", "scheduled": "publish", "live": "publish"}
    for stage, step in steps.items():
        assert wiz.step_for(Video(stage=stage)) == step, stage
    assert wiz.step_for(None) == "topic"
    assert wiz.finished(Video(stage="scheduled")) and not wiz.finished(Video(stage="reviewed"))


def test_resume_video_skips_live(ctx):
    a = research.approve(ctx, svc.add_manual_topic(ctx, "how airlines make money").id)
    b = research.approve(ctx, svc.add_manual_topic(ctx, "how banks make money").id)
    b.stage = "live"
    ctx.session.commit()
    assert wiz.resume_video(ctx).id == a.id


def test_channel_type_drives_wizard_mode(root):
    assert channels.type_info(root)["mode"] == "narrated"
    cid = channels.add(root, "Tiny Tunes", type="kids")
    assert channels.type_info(root, cid)["mode"] == "kids"


# ---------- launchers ----------
def test_windows_launcher_is_complete_and_crlf():
    raw = (REPO / "run_app.bat").read_bytes()
    text = raw.decode()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    for needle in ("venv", "pip install -r requirements.txt", "streamlit run app.py", "ffmpeg", ".env.example"):
        assert needle in text
    assert (REPO / "run_app.sh").read_text().startswith("#!/usr/bin/env bash")


# ---------- Streamlit smoke ----------
def _app(root, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("STUDIO_HOME", str(root))
    return AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()


def test_new_pages_render(root, monkeypatch):
    at = _app(root, monkeypatch)
    assert not at.exception
    for page in ["🎬 Make a video", "Setup", "📊 Analytics", "Channels", "Home"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page


def test_wizard_topic_to_script_step(root, monkeypatch):
    at = _app(root, monkeypatch)
    at.sidebar.radio[0].set_value("🎬 Make a video").run()
    assert any("Step 1" in s.value for s in at.subheader)
    own = next(t for t in at.text_input if t.key == "wz_own")
    own.set_value("how Costco makes money").run()
    next(b for b in at.button if b.key == "wz_own_btn").click().run()
    assert not at.exception
    assert any("Step 2" in s.value for s in at.subheader)
    next(b for b in at.button if b.key == "wz_sreq").click().run()
    assert not at.exception
    assert any(c.language == "markdown" for c in at.code)  # the prompt to copy into Claude is shown


def test_wizard_for_kids_channel_shows_kids_builder(root, monkeypatch):
    channels.add(root, "Tiny Tunes", type="kids")
    at = _app(root, monkeypatch)
    at.sidebar.radio[0].set_value("🎬 Make a video").run()
    assert not at.exception and any("Kids mode" in h.value for h in at.header)


def test_setup_page_lists_every_section(root, monkeypatch):
    at = _app(root, monkeypatch)
    at.sidebar.radio[0].set_value("Setup").run()
    assert not at.exception
    labels = " ".join(e.label for e in at.expander)
    for title in ("Video tools", "Script writer", "Narration voice", "Google client file", "Sign in to Google"):
        assert title in labels
