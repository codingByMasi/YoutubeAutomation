"""Production settings (renderer, voice, music, colours) resolved per video, channel and channel type.

Order of precedence, strongest first: the video's own `projects/<id>/production.json`, the channel profile,
the channel type's default, then `.env`. Works for every channel type and video type.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from studio.config import Settings
from studio.errors import StudioError
from studio.growth import channel_types, channels

VIDEO_FIELDS = ("renderer", "voice", "music", "music_mood", "tts_provider")


def _video_file(settings: Settings, video_id: int) -> Path:
    return settings.project_dir(video_id) / "production.json"


def video_overrides(settings: Settings, video_id: int) -> dict:
    """The per-video overrides saved for a video ({} when none)."""
    f = _video_file(settings, video_id)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def set_video(settings: Settings, video_id: int, **values) -> dict:
    """Save per-video overrides (blank clears a field). Unknown or invalid values raise a helpful error."""
    cur = video_overrides(settings, video_id)
    for k, v in values.items():
        if v is None:
            continue
        if k not in VIDEO_FIELDS:
            raise StudioError(f"Unknown production setting '{k}'.", f"Known: {', '.join(VIDEO_FIELDS)}.",
                              "Use one of those names.")
        v = str(v).strip()
        if k in channel_types.CHOICES and v.lower() not in channel_types.CHOICES[k]:
            raise StudioError(f"'{v}' is not a valid {k}.",
                              f"Choose one of: {', '.join(a for a in channel_types.CHOICES[k] if a)}.",
                              f"Set {k} again, or leave it blank to use the channel default.")
        if v:
            cur[k] = v.lower() if k in channel_types.CHOICES else v
        else:
            cur.pop(k, None)
    _video_file(settings, video_id).write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return cur


def clear_video(settings: Settings, video_id: int) -> None:
    """Remove a video's overrides so it follows its channel again."""
    _video_file(settings, video_id).unlink(missing_ok=True)


def resolve(settings: Settings, video_id: int | None = None, channel_id: str | None = None) -> dict:
    """Effective settings: renderer, voice, tts_provider, music, music_mood, palette and where each came from."""
    cid = channel_id or channels.active_id(settings.root)
    prof = channels.get(settings.root, cid)
    t = channel_types.info(prof["type"])
    over = video_overrides(settings, video_id) if video_id is not None else {}
    out, src = {}, {}

    def pick(key: str, *layers: tuple[str, str]) -> None:
        for name, val in layers:
            if val:
                out[key], src[key] = val, name
                return
        out[key], src[key] = "", "default"

    pick("renderer", ("video", over.get("renderer", "")), ("channel", prof["renderer"]), (".env", settings.renderer))
    pick("voice", ("video", over.get("voice", "")), ("channel", prof["voice"]), (".env", settings.tts_voice))
    pick("tts_provider", ("video", over.get("tts_provider", "")), ("channel", prof["tts_provider"]),
         (".env", settings.tts_provider))
    pick("music", ("video", over.get("music", "")), ("channel", prof["music"]), ("type", "generated"))
    pick("music_mood", ("video", over.get("music_mood", "")), ("channel", prof["music_mood"]),
         ("type", t["music_mood"]))
    custom = (prof["brand_primary"], prof["brand_accent"]) != (channels.DEFAULTS["brand_primary"],
                                                              channels.DEFAULTS["brand_accent"])
    out["palette"] = (prof["brand_primary"], prof["brand_accent"]) if custom else t["palette"]
    src["palette"] = "channel" if custom else ("type" if t["palette"] else "default")
    out["sources"] = src
    out["type"], out["mode"] = prof["type"], t["mode"]
    return out


def apply(settings: Settings, video_id: int | None = None, channel_id: str | None = None) -> Settings:
    """Settings copy with the resolved voice, TTS provider, renderer and Made-for-Kids flag applied."""
    r = resolve(settings, video_id, channel_id)
    return replace(settings, tts_voice=r["voice"], tts_provider=r["tts_provider"], renderer=r["renderer"],
                   made_for_kids=channel_types.info(r["type"])["made_for_kids"])


def describe(settings: Settings, video_id: int | None = None, channel_id: str | None = None) -> str:
    """Readable table of the effective settings and where each value comes from."""
    r = resolve(settings, video_id, channel_id)
    lines = [f"Channel type: {r['type']} (pipeline: {r['mode']})"]
    lines += [f"  {k:13} {r[k] or '(default)':22} from {r['sources'][k]}"
              for k in ("renderer", "voice", "tts_provider", "music", "music_mood")]
    lines.append(f"  {'colours':13} {r['palette'] or '(brand defaults)'}  from {r['sources']['palette']}")
    return "\n".join(lines)
