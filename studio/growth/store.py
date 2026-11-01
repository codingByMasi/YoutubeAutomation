"""Tiny JSON storage for growth data under <root>/growth/ (channel-wide) or projects/<id>/growth/ (per video)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from studio.errors import StudioError


def load(path: Path, default: Any) -> Any:
    """Read JSON from path, or return `default` if it does not exist yet."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StudioError(f"{path.name} is not valid JSON.", str(exc),
                          f"Fix or delete {path} and try again.") from exc


def save(path: Path, data: Any) -> Path:
    """Write JSON to path, creating folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def global_file(root: Path, name: str) -> Path:
    """Data shared by all channels (the channel list itself)."""
    return root / "growth" / f"{name}.json"


def channel_file(root: Path, name: str) -> Path:
    """Data for the active channel. The "default" channel keeps the original growth/<name>.json paths."""
    active = load(global_file(root, "channels"), {}).get("active", "default")
    if active == "default":
        return global_file(root, name)
    return root / "growth" / "c" / active / f"{name}.json"


def video_file(project_dir: Path, name: str) -> Path:
    return project_dir / "growth" / f"{name}.json"


def extract_json(text: str) -> dict:
    """Parse the first JSON object in pasted text (tolerates ```json fences and chatter)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise StudioError("No JSON object found in the pasted text.", "The answer must be a JSON object.",
                          "Ask Claude to reply with ONLY the JSON, then paste it again.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise StudioError("The pasted JSON could not be read.", str(exc),
                          "Ask Claude to fix the JSON and paste it again.") from exc
