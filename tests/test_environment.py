import subprocess
import sys

import pytest
from typer.testing import CliRunner

from studio.cli import app
from studio.errors import StudioError
from studio.manage import doctor, environment


def test_run_checks_never_raises_and_covers_areas(ctx):
    checks = environment.run_checks(ctx.settings, network=False)
    assert checks and all(c.level in (doctor.OK, doctor.WARN, doctor.FAIL) for c in checks)
    assert any("Python" in c.message for c in checks)


def test_a_crashing_check_becomes_a_warning(ctx, monkeypatch):
    def boom():
        raise RuntimeError("x")
    monkeypatch.setattr(environment, "check_python", boom)
    checks = environment.run_checks(ctx.settings, network=False)
    assert any("could not run" in c.message and c.level == doctor.WARN for c in checks)


def test_missing_required_package_fails_with_pip_fix(monkeypatch):
    monkeypatch.setattr(environment, "_importable", lambda name: name != "edge_tts")
    out = environment.check_packages()
    bad = [c for c in out if c.level == doctor.FAIL]
    assert bad and bad[0].action == "pip:edge-tts"


def test_missing_optional_package_only_warns(monkeypatch):
    monkeypatch.setattr(environment, "_importable", lambda name: name != "faster_whisper")
    out = environment.check_packages()
    assert [c.level for c in out] == [doctor.WARN] and out[0].action == "pip:faster-whisper"


def test_unsupported_python_is_reported(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
    assert environment.check_python().level == doctor.FAIL


def test_low_disk_fails(ctx, monkeypatch):
    monkeypatch.setattr(environment.shutil, "disk_usage", lambda _p: type("U", (), {"free": 5e8})())
    assert environment.check_disk(ctx.settings).level == doctor.FAIL


def test_offline_is_a_warning_not_a_failure():
    def refuse(*_a, **_k):
        raise OSError("no route")
    assert environment.check_internet(refuse).level == doctor.WARN


def test_fonts_load_a_real_truetype_font(ctx):
    assert environment.check_fonts(ctx.settings).level == doctor.OK


def test_folders_are_created_and_writable(ctx):
    assert environment.check_folders(ctx.settings)[0].level == doctor.OK


def test_pip_fix_runs_pip_and_reports_failure(ctx, monkeypatch):
    calls = []

    def fake_run(cmd, **_k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(environment.subprocess, "run", fake_run)
    assert "Installed" in environment.apply_fix("pip:rapidfuzz", ctx.settings)
    assert calls[0][-1] == "rapidfuzz" and calls[0][:3] == [sys.executable, "-m", "pip"]
    monkeypatch.setattr(environment.subprocess, "run",
                        lambda cmd, **_k: subprocess.CompletedProcess(cmd, 1, "", "ERROR: no network"))
    with pytest.raises(StudioError) as e:
        environment.apply_fix("pip:rapidfuzz", ctx.settings)
    assert "internet" in str(e.value)


def test_unknown_fix_is_refused(ctx):
    with pytest.raises(StudioError):
        environment.apply_fix("rm -rf", ctx.settings)


def test_runtime_defaults_silence_hf_symlink_warning(monkeypatch):
    monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS_WARNING", raising=False)
    environment.set_runtime_defaults()
    import os
    assert os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] == "1"


def test_preflight_cli_runs(ctx):
    res = CliRunner().invoke(app, ["preflight", "--offline"])
    assert res.exit_code in (0, 1) and "Python" in res.output
