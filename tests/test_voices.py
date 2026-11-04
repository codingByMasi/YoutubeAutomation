"""Voices page: narration choice persists, voicebank list shows licence/monetisation, AyaLuna needs acknowledgement."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio.config import load_settings
from studio.errors import StudioError
from studio.growth import channels
from studio.web import setup_service as setup
from studio.web import voices_service as vs

REPO = Path(__file__).parent.parent


@pytest.fixture
def root(tmp_path, monkeypatch):
    for k in setup.ENV_KEYS:
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return tmp_path


def test_select_narration_persists_to_env_and_channel(root):
    vs.select_narration(root, "en-GB-RyanNeural")
    s = load_settings(root)
    assert s.tts_voice == "en-GB-RyanNeural" and s.tts_provider == "edge"
    assert channels.get(root)["voice"] == "en-GB-RyanNeural"
    assert [v["id"] for v in vs.narration_voices(s) if v["selected"]] == ["en-GB-RyanNeural"]


def test_empty_narration_refused(root):
    with pytest.raises(StudioError):
        vs.select_narration(root, " ")


def test_cards_show_licence_monetisation_and_ai_warning(root):
    card = vs.voicebank_cards(load_settings(root))[0]
    assert card["key"] == "ayaluna-english" and card["ai_warning"] is True
    assert "Monetising allowed" in card["monetisation"] and card["licence"] and card["credit"]
    assert any("AI generated" in w for w in card["warnings"])
    assert card["installed"] is False and card["preview"] is None and card["selected"] is False


def test_ayaluna_needs_acknowledgement_then_persists(root):
    with pytest.raises(StudioError, match="bans AI-generated"):
        vs.select_voicebank(root, "ayaluna-english")
    assert load_settings(root).sing_voicebank == ""
    vs.select_voicebank(root, "ayaluna-english", acknowledged=True)
    s = load_settings(root)
    assert s.sing_voicebank == "ayaluna-english"
    assert vs.voicebank_cards(s)[0]["selected"] is True
    vs.select_voicebank(root, "")
    assert load_settings(root).sing_voicebank == ""


def test_unvetted_voicebank_refused(root):
    with pytest.raises(StudioError, match="not on the approved list"):
        vs.select_voicebank(root, "random-bank", acknowledged=True)
    with pytest.raises(StudioError):
        setup.save_env(root, {"SING_VOICEBANK": "random-bank"})


def test_preview_upload(root):
    vs.save_preview(root, "ayaluna-english", "demo.wav", b"RIFFdata")
    assert vs.preview_path(root, "ayaluna-english").read_bytes() == b"RIFFdata"
    with pytest.raises(StudioError):
        vs.save_preview(root, "ayaluna-english", "x.exe", b"1")
    with pytest.raises(StudioError):
        vs.save_preview(root, "unvetted", "x.wav", b"1")


def test_openutau_and_installed_detection(root, tmp_path):
    exe = tmp_path / "OpenUtau" / "OpenUtau.exe"
    (tmp_path / "OpenUtau" / "Singers" / "AyaLuna English").mkdir(parents=True)
    exe.write_bytes(b"")
    s = load_settings(root)
    s.openutau_path = str(exe)
    assert vs.openutau_status(s)["found"]
    assert vs.voicebank_cards(s)[0]["installed"] is True
    s.openutau_path = str(tmp_path / "missing.exe")
    assert not vs.openutau_status(s)["found"]
    with pytest.raises(StudioError):
        vs.open_in_openutau(s)


def test_voices_page_renders(root, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("STUDIO_HOME", str(root))
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=30).run()
    at.sidebar.radio[0].set_value("🎙️ Voices").run()
    assert not at.exception
    assert any("Narration voice" in s.value for s in at.subheader)
    assert any("AI generated" in e.value for e in at.error)
    next(b for b in at.button if b.key == "use_en-GB-RyanNeural").click().run()
    assert not at.exception and load_settings(root).tts_voice == "en-GB-RyanNeural"
    # AyaLuna: unchecked box refuses, checked box saves
    next(b for b in at.button if b.key == "usevb_ayaluna-english").click().run()
    assert load_settings(root).sing_voicebank == ""
    next(c for c in at.checkbox if c.key == "ack_ayaluna-english").check().run()
    next(b for b in at.button if b.key == "usevb_ayaluna-english").click().run()
    assert load_settings(root).sing_voicebank == "ayaluna-english"
