"""YouTube sign-in status, token persistence and the shared studio folder."""

import json

from studio import config, health
from studio.config import Settings
from studio.youtube import auth

TOKEN = {"token": "a", "refresh_token": "r", "client_id": "c", "client_secret": "s",
         "token_uri": "https://oauth2.googleapis.com/token", "scopes": auth.SCOPES}


def _settings(tmp_path, channel="default"):
    (tmp_path / "client_secret.json").write_text('{"installed": {}}')
    return Settings(root=tmp_path, channel_key=channel)


def test_default_home_is_not_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STUDIO_HOME", raising=False)
    assert config.load_settings().root == config.DEFAULT_HOME


def test_missing_and_no_client(tmp_path):
    s = Settings(root=tmp_path)
    assert auth.status(s)["state"] == "no_client"
    s = _settings(tmp_path)
    assert auth.status(s)["state"] == "missing"


def test_connected_without_network(tmp_path):
    s = _settings(tmp_path)
    s.token_path.write_text(json.dumps(TOKEN))
    r = auth.status(s)
    assert r["state"] == "connected" and "token" in r and r["message"] != "a"


def test_no_refresh_token_or_bad_scope_is_expired(tmp_path):
    s = _settings(tmp_path)
    s.token_path.write_text(json.dumps({**TOKEN, "refresh_token": None}))
    assert auth.status(s)["state"] == "expired"
    s.token_path.write_text(json.dumps({**TOKEN, "scopes": ["https://www.googleapis.com/auth/youtube.upload"]}))
    assert auth.status(s)["state"] == "expired"


def test_legacy_token_adopted_only_on_request(tmp_path):
    s = _settings(tmp_path, "finance")
    (tmp_path / "token.json").write_text(json.dumps(TOKEN))
    assert auth.status(s)["state"] == "missing" and not s.token_path.exists()
    assert auth.status(s, adopt=True)["state"] == "connected" and s.token_path.exists()


def test_signin_problem_is_logged_with_fix(tmp_path):
    health.record_signin_problems(tmp_path, [{"channel_id": "kids", "state": "expired", "message": "gone"}])
    (issue,) = health.open_issues(tmp_path)
    assert issue["fix"] == "youtube_signin" and issue["fix_label"]


def test_dead_grant_detection():
    assert auth._is_dead_grant(Exception("invalid_grant: Token has been expired or revoked."))
    assert not auth._is_dead_grant(Exception("connection reset"))
