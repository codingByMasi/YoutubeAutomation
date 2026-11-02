"""LLM wrapper.

Default provider `claude_code` needs no API key: the command writes a prompt file, stops, and
Claude Code (in a session on this repo) writes the JSON answer next to it. Re-running the
command validates the answer and continues. API providers are optional plug-ins.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from studio.config import API_LLM_PROVIDERS, Settings
from studio.errors import InvalidAnswer, PendingLLMResponse, StudioError
from studio.util.answer_json import parse_answer
from studio.util.retry import with_retry

Validator = Callable[[dict], list[str]]  # returns a list of problems; empty means valid


def prompt_paths(work_dir: Path, task: str) -> tuple[Path, Path]:
    """(prompt file, response file) for a task inside a project folder."""
    d = work_dir / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{task}.prompt.md", d / f"{task}.response.json"


def _extract_json(text: str) -> dict:
    """Parse the first JSON object in text (tolerates fences, chatter, smart quotes, trailing commas)."""
    return parse_answer(text)


def _load_response(path: Path, validate: Validator | None) -> dict:
    try:
        data = _extract_json(path.read_text(encoding="utf-8"))
    except StudioError as exc:
        raise StudioError(f"{path.name}: {exc.what}", exc.why, exc.next_step) from exc
    try:
        problems = validate(data) if validate else []
    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        keys = ", ".join(sorted(map(str, data))[:12]) or "none"
        problems = [f"the answer is not shaped as the request asked ({type(exc).__name__}: {exc}). "
                    f"Top-level keys found: {keys}"]
    if problems:
        bullet = "\n  - ".join(problems)
        prompt_name = path.name.replace(".response.json", ".prompt.md")
        raise InvalidAnswer(
            f"The answer in {path.name} failed validation:\n  - {bullet}",
            "The output must follow the rules in the prompt file.",
            f"Ask Claude to fix exactly the points above (it has the request), then paste the corrected JSON "
            f"(or in Claude Code: fix {path} using {prompt_name}).",
            problems, str(path),
        )
    return data


def _handoff_text(prompt: str, response_path: Path) -> str:
    return (
        f"{prompt}\n\n---\n\n## How to answer\n\nWrite ONLY a JSON object (no prose) to "
        f"`{response_path.as_posix()}`. Then re-run the studio command that created this prompt.\n"
    )


def prompt_hash(prompt: str) -> str:
    """Stable short hash of a prompt; the cache key of its answer."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _meta_path(response_file: Path) -> Path:
    return response_file.with_name(response_file.name.replace(".response.json", ".meta.json"))


def _stale(response_file: Path, prompt: str) -> bool:
    """True if the saved answer was written for a different prompt (topic, facts or rules changed).

    Answers with no recorded hash (older projects, hand-placed files) are trusted."""
    meta = _meta_path(response_file)
    if not meta.exists():
        return False
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("prompt_hash") != prompt_hash(prompt)
    except (ValueError, OSError):
        return False


def _archive_stale(response_file: Path) -> Path:
    """Move an out-of-date answer aside (never deleted) so it is not silently reused."""
    n = 1
    while (dest := response_file.with_name(response_file.name.replace(".response.json", f".stale{n}.json"))).exists():
        n += 1
    response_file.rename(dest)
    return dest


def _call_api(settings: Settings, prompt: str, provider: str | None = None) -> str:
    settings.require("script (LLM API provider)", "LLM_API_KEY", "LLM_MODEL")
    p = provider or settings.llm_provider
    try:
        if p == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=settings.llm_api_key)
            msg = client.messages.create(model=settings.llm_model, max_tokens=16000,
                                         messages=[{"role": "user", "content": prompt}])
            if getattr(msg, "stop_reason", "") == "max_tokens":
                raise _truncated(p)
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if p == "openai":
            import openai

            client = openai.OpenAI(api_key=settings.llm_api_key)
            r = client.chat.completions.create(model=settings.llm_model,
                                               messages=[{"role": "user", "content": prompt}])
            if getattr(r.choices[0], "finish_reason", "") == "length":
                raise _truncated(p)
            return r.choices[0].message.content or ""
        if p == "gemini":
            from google import genai

            client = genai.Client(api_key=settings.llm_api_key)
            resp = client.models.generate_content(model=settings.llm_model, contents=prompt)
            cands = getattr(resp, "candidates", None) or []
            if cands and "MAX_TOKENS" in str(getattr(cands[0], "finish_reason", "")):
                raise _truncated(p)
            return resp.text or ""
    except ImportError as exc:
        raise StudioError(f"The Python package for LLM_PROVIDER={p} is not installed.", str(exc),
                          "pip install the package listed under optional extras in requirements.txt.") from exc
    raise StudioError(f"Unknown LLM provider {p}.", "", "Set LLM_PROVIDER=claude_code in .env.")


def _truncated(provider: str) -> StudioError:
    return StudioError(f"The {provider} answer was cut off (max_tokens reached), so the JSON is incomplete.",
                       "The output is longer than the token limit allows.",
                       "Re-run (the cut-off answer was not saved), or shorten the request / use a model with a "
                       "larger output limit.")


def pending_task(work_dir: Path, task: str) -> str:
    """'done' (valid-looking answer present), 'waiting' (prompt written, no answer) or 'new'."""
    prompt_file, response_file = prompt_paths(work_dir, task)
    if response_file.exists():
        return "done"
    return "waiting" if prompt_file.exists() else "new"


def ask_json(settings: Settings, work_dir: Path, task: str, prompt: str,
             validate: Validator | None = None, force: bool = False, api_provider: str | None = None,
             handoff_only: bool = False, model: type | None = None) -> dict:
    """Get a validated JSON answer for `prompt`, cached at prompts/<task>.response.json.

    The cache key is the hash of the prompt: an answer written for a different prompt is archived as
    `<task>.stale<N>.json` and the task is asked again. `api_provider` (e.g. LLM_CRITIC_PROVIDER) lets one task
    use an API provider while the rest keep the file handoff; empty means handoff. `handoff_only` forces the
    file handoff even when LLM_PROVIDER is an API (the facts step needs web search, which APIs here lack)."""
    prompt_file, response_file = prompt_paths(work_dir, task)
    if model is not None:  # Pydantic shape check first, then the task's own rules
        from studio.story.models import model_problems
        inner = validate

        def validate(data: dict, _inner=inner) -> list[str]:  # noqa: F811
            return model_problems(model, data) or (_inner(data) if _inner else [])
    if force:
        response_file.unlink(missing_ok=True)
    handoff = _handoff_text(prompt, response_file)
    if response_file.exists() and _stale(response_file, handoff):
        old = _archive_stale(response_file)
        print(f"Note: the saved {task} answer was written for a different prompt; kept as {old.name}.")
    if response_file.exists():
        return _load_response(response_file, validate)
    prompt_file.write_text(handoff, encoding="utf-8")
    _meta_path(response_file).write_text(json.dumps({"prompt_hash": prompt_hash(handoff)}), encoding="utf-8")
    provider = "" if handoff_only else api_provider or (
        settings.llm_provider if settings.llm_provider in API_LLM_PROVIDERS else "")
    if provider in API_LLM_PROVIDERS:
        text = with_retry(lambda: _call_api(settings, prompt, provider), f"LLM call ({provider})")
        response_file.write_text(text, encoding="utf-8")
        return _load_response(response_file, validate)
    raise PendingLLMResponse(
        f"Prompt written to {prompt_file}.",
        "LLM_PROVIDER=claude_code: Claude Code writes the answer instead of an API.",
        f"In Claude Code, say: \"Answer the prompt in {prompt_file.as_posix()}\". "
        "When it has written the response file, re-run this command.",
    )
