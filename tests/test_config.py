import pytest

from studio.config import load_settings
from studio.errors import ConfigError


def test_defaults_need_no_llm_key(root):
    s = load_settings(root)
    assert s.llm_provider == "claude_code"
    assert s.daily_quota_limit == 10000 and s.quota_safety_margin == 500


def test_env_file_is_read(root):
    (root / ".env").write_text("PEXELS_API_KEY=abc123\nDAILY_QUOTA_LIMIT=2000\n")
    s = load_settings(root)
    assert s.pexels_api_key == "abc123" and s.daily_quota_limit == 2000
    assert "abc123" in s.secrets


def test_missing_key_names_variable_and_command(root):
    s = load_settings(root)
    with pytest.raises(ConfigError) as e:
        s.require("visuals")
    msg = str(e.value)
    assert "PEXELS_API_KEY" in msg and "`visuals`" in msg and ".env" in msg


def test_missing_client_secret_file_is_explained(root):
    (root / ".env").write_text("CHANNEL_ID=UC123\n")
    s = load_settings(root)
    with pytest.raises(ConfigError) as e:
        s.require("publish")
    assert "client_secret" in str(e.value).lower() and "`publish`" in str(e.value)


def test_api_llm_provider_requires_key_and_model(root):
    (root / ".env").write_text("LLM_PROVIDER=anthropic\n")
    s = load_settings(root)
    with pytest.raises(ConfigError) as e:
        s.require("script", "LLM_API_KEY", "LLM_MODEL")
    assert "LLM_API_KEY" in str(e.value)


@pytest.mark.parametrize("line,word", [("LLM_PROVIDER=foo", "LLM_PROVIDER"), ("TTS_PROVIDER=bar", "TTS_PROVIDER"),
                                       ("DAILY_QUOTA_LIMIT=lots", "DAILY_QUOTA_LIMIT"),
                                       ("QUOTA_SAFETY_MARGIN=20000", "QUOTA_SAFETY_MARGIN")])
def test_invalid_values_rejected(root, line, word):
    (root / ".env").write_text(line + "\n")
    with pytest.raises(ConfigError) as e:
        load_settings(root)
    assert word in str(e.value)
