import json

from typer.testing import CliRunner

from studio.cli import app
from studio.manage import doctor


def levels(checks, area):
    return {c.level for c in checks if c.area == area}


def test_no_go_without_youtube_setup(ctx, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _t: "/usr/bin/x")
    checks = doctor.run_checks(ctx.settings)
    assert doctor.verdict(checks) == "NO-GO"
    assert "fail" in levels(checks, "YouTube upload")


def test_go_with_full_setup(ctx, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _t: "/usr/bin/x")
    s = ctx.settings
    s.client_secret.write_text(json.dumps({"installed": {"client_id": "x"}}))
    s.channel_id = "UCabc"
    s.token_path.write_text("{}")
    s.tts_provider = "edge"
    checks = doctor.run_checks(s)
    assert doctor.verdict(checks) == "GO"
    assert "Verdict: GO" in doctor.render(checks)


def test_web_client_is_rejected_and_missing_ffmpeg_fails(ctx, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _t: None)
    ctx.settings.client_secret.write_text(json.dumps({"web": {}}))
    checks = doctor.run_checks(ctx.settings)
    assert any("Desktop app" in c.fix for c in checks)
    assert "fail" in levels(checks, "Video tools")


def test_silent_voice_blocks(ctx, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _t: "/usr/bin/x")
    ctx.settings.tts_provider = "silent"
    assert "fail" in levels(doctor.run_checks(ctx.settings), "Voice")


def test_add_topic_and_suggest_cli(root, monkeypatch):
    monkeypatch.setenv("STUDIO_HOME", str(root))
    r = CliRunner().invoke(app, ["add-topic", "how Costco makes money", "--approve"])
    assert r.exit_code == 0, r.output
    assert "Saved topic" in r.output
    r = CliRunner().invoke(app, ["add-topic", "  "])
    assert r.exit_code != 0
