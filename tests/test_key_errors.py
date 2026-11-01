"""A rejected stock-footage key (HTTP 401) must never crash a build; it falls back with a friendly notice."""

from __future__ import annotations

import io
import urllib.error

import pytest

from studio.config import clean_secret, load_settings
from studio.errors import RequestRejected
from studio.manage import doctor
from studio.providers.footage import make_footage
from studio.providers.guard import Guarded
from studio.providers.images import make_images
from studio.providers.pixabay import Pixabay
from studio.util.retry import with_retry


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://pixabay.com/api/", code, "Unauthorized", {}, io.BytesIO(b""))


def rejecting_opener(code: int = 401):
    def opener(req, timeout=0):
        raise http_error(code)
    return opener


def test_non_retryable_http_error_becomes_plain_error():
    def boom():
        raise http_error(401)
    with pytest.raises(RequestRejected) as e:
        with_retry(boom, "Pixabay search")
    assert e.value.code == 401 and "invalid API key" in str(e.value)


def test_guarded_provider_swallows_401_and_notifies_once(tmp_path):
    notes: list[str] = []
    g = Guarded(Pixabay("bad", tmp_path, opener=rejecting_opener()), "Pixabay", "PIXABAY_API_KEY", notes.append)
    assert g.find(["city"]) is None
    assert g.find(["bank"]) is None  # disabled: no second request, no second notice
    assert len(notes) == 1
    assert "Pixabay" in notes[0] and "PIXABAY_API_KEY" in notes[0] and "quotes" in notes[0]


def test_guarded_provider_survives_unexpected_errors(tmp_path):
    class Broken:
        def find(self, kw, exclude=None):
            raise ValueError("weird")
    notes: list[str] = []
    g = Guarded(Broken(), "Pixabay", "PIXABAY_API_KEY", notes.append)
    for _ in range(3):
        assert g.find(["x"]) is None
    assert len(notes) == 1 and g.disabled


def test_make_footage_and_images_are_guarded(root, monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "abc")
    s = load_settings(root)
    assert isinstance(make_footage(s)[1], Guarded)
    _, search = make_images(s)
    assert any(isinstance(src, Guarded) for src in search.sources)


def test_clean_secret_strips_quotes_spaces_and_bom():
    assert clean_secret('  "12345-abcdef"  ') == "12345-abcdef"
    assert clean_secret("'12345-abc'") == "12345-abc"
    assert clean_secret("﻿12345 abc") == "12345abc"
    assert clean_secret(None) == ""


def test_env_file_with_quotes_and_misspelled_name(root):
    (root / ".env").write_text('PIXABAY_KEY = " 123-abc "\n', encoding="utf-8-sig")
    assert load_settings(root).pixabay_api_key == "123-abc"
    (root / ".env").write_text("PIXABAY_API_KEY='123-abc'\n")
    assert load_settings(root).pixabay_api_key == "123-abc"


def test_doctor_key_test_reports_rejected_key(root, monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "bad")
    checks = doctor.test_footage_keys(load_settings(root), rejecting_opener())
    assert checks[0].level == doctor.FAIL and "PIXABAY_API_KEY" in checks[0].fix


def test_doctor_key_test_ok_offline_and_missing(root, monkeypatch):
    assert doctor.test_footage_keys(load_settings(root))[0].level == doctor.WARN  # no key
    monkeypatch.setenv("PIXABAY_API_KEY", "good")

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"
    assert doctor.test_footage_keys(load_settings(root), lambda r, timeout=0: R())[0].level == doctor.OK

    def offline(req, timeout=0):
        raise urllib.error.URLError("no network")
    assert doctor.test_footage_keys(load_settings(root), offline)[0].level == doctor.WARN
