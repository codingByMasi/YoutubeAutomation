import logging
import urllib.error

import pytest

from studio.errors import PendingLLMResponse, StudioError
from studio.llm import ask_json, prompt_paths
from studio.util.logging import RedactSecrets
from studio.util.retry import with_retry


def test_retry_recovers_from_transient_errors():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("reset")
        return "ok"

    assert with_retry(flaky, "thing", sleep=lambda s: None) == "ok" and len(calls) == 3


def test_retry_gives_up_after_five_with_context():
    calls = []

    def down():
        calls.append(1)
        raise urllib.error.HTTPError("u", 503, "unavailable", {}, None)

    with pytest.raises(StudioError) as e:
        with_retry(down, "Pexels search", sleep=lambda s: None)
    assert len(calls) == 5 and "Pexels search failed after 5 attempts" in str(e.value)


def test_retry_does_not_retry_client_errors():
    calls = []

    def bad():
        calls.append(1)
        raise urllib.error.HTTPError("u", 400, "bad", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        with_retry(bad, "x", sleep=lambda s: None)
    assert len(calls) == 1


def test_secrets_are_redacted():
    rec = logging.LogRecord("studio", logging.INFO, "", 0, "key is %s", ("sk-SECRET-123",), None)
    RedactSecrets(["sk-SECRET-123"]).filter(rec)
    assert rec.getMessage() == "key is ***"


def test_claude_code_handoff_writes_prompt_then_reads_answer(ctx, tmp_path):
    with pytest.raises(PendingLLMResponse) as e:
        ask_json(ctx.settings, tmp_path, "script", "Write a script.")
    assert e.value.exit_code == 3
    prompt_file, response_file = prompt_paths(tmp_path, "script")
    assert "Write a script." in prompt_file.read_text() and response_file.name in prompt_file.read_text()
    response_file.write_text('```json\n{"ok": true}\n```')
    assert ask_json(ctx.settings, tmp_path, "script", "Write a script.") == {"ok": True}


def test_invalid_answer_reports_problems(ctx, tmp_path):
    _, response_file = prompt_paths(tmp_path, "t")
    response_file.write_text('{"titles": []}')
    with pytest.raises(StudioError) as e:
        ask_json(ctx.settings, tmp_path, "t", "p", validate=lambda d: ["need 15 titles"])
    assert "need 15 titles" in str(e.value)
