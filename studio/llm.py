"""LLM wrapper.

Default provider `claude_code` needs no API key: the command writes a prompt file, stops, and
Claude Code (in a session on this repo) writes the JSON answer next to it. Re-running the
command validates the answer and continues. API providers are optional plug-ins.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from studio.config import API_LLM_PROVIDERS, Settings
from studio.errors import PendingLLMResponse, StudioError
from studio.util.retry import with_retry

Validator = Callable[[dict], list[str]]  # returns a list of problems; empty means valid


def prompt_paths(work_dir: Path, task: str) -> tuple[Path, Path]:
    """(prompt file, response file) for a task inside a project folder."""
    d = work_dir / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{task}.prompt.md", d / f"{task}.response.json"


def _extract_json(text: str) -> dict:
    """Parse the first JSON object in text (tolerates ```json fences)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def _load_response(path: Path, validate: Validator | None) -> dict:
    try:
        data = _extract_json(path.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise StudioError(f"{path} is not valid JSON.", str(exc), f"Fix or delete {path.name} and re-run.") from exc
    problems = validate(data) if validate else []
    if problems:
        bullet = "\n  - ".join(problems)
        raise StudioError(
            f"The answer in {path} failed validation:\n  - {bullet}",
            "The output must follow the rules in the prompt file.",
            f"Ask Claude Code to fix {path} using {path.with_name(path.name.replace('.response.json', '.prompt.md'))},"
            " then re-run the command.",
        )
    return data


def _handoff_text(prompt: str, response_path: Path) -> str:
    return (
        f"{prompt}\n\n---\n\n## How to answer\n\nWrite ONLY a JSON object (no prose) to "
        f"`{response_path.as_posix()}`. Then re-run the studio command that created this prompt.\n"
    )


def _call_api(settings: Settings, prompt: str) -> str:
    settings.require("script (LLM API provider)", "LLM_API_KEY", "LLM_MODEL")
    p = settings.llm_provider
    try:
        if p == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=settings.llm_api_key)
            msg = client.messages.create(model=settings.llm_model, max_tokens=16000,
                                         messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if p == "openai":
            import openai

            client = openai.OpenAI(api_key=settings.llm_api_key)
            r = client.chat.completions.create(model=settings.llm_model,
                                               messages=[{"role": "user", "content": prompt}])
            return r.choices[0].message.content or ""
        if p == "gemini":
            from google import genai

            client = genai.Client(api_key=settings.llm_api_key)
            return client.models.generate_content(model=settings.llm_model, contents=prompt).text or ""
    except ImportError as exc:
        raise StudioError(f"The Python package for LLM_PROVIDER={p} is not installed.", str(exc),
                          "pip install the package listed under optional extras in requirements.txt.") from exc
    raise StudioError(f"Unknown LLM provider {p}.", "", "Set LLM_PROVIDER=claude_code in .env.")


def ask_json(settings: Settings, work_dir: Path, task: str, prompt: str,
             validate: Validator | None = None, force: bool = False) -> dict:
    """Get a validated JSON answer for `prompt`, cached at prompts/<task>.response.json."""
    prompt_file, response_file = prompt_paths(work_dir, task)
    if force:
        response_file.unlink(missing_ok=True)
    if response_file.exists():
        return _load_response(response_file, validate)
    prompt_file.write_text(_handoff_text(prompt, response_file), encoding="utf-8")
    if settings.llm_provider in API_LLM_PROVIDERS:
        text = with_retry(lambda: _call_api(settings, prompt), f"LLM call ({settings.llm_provider})")
        response_file.write_text(text, encoding="utf-8")
        return _load_response(response_file, validate)
    raise PendingLLMResponse(
        f"Prompt written to {prompt_file}.",
        "LLM_PROVIDER=claude_code: Claude Code writes the answer instead of an API.",
        f"In Claude Code, say: \"Answer the prompt in {prompt_file.as_posix()}\". "
        "When it has written the response file, re-run this command.",
    )
