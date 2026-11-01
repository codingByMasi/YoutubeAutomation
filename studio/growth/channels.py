"""Channel profiles: any number, added/edited/switched at any time. One is active; the rest wait.

Stored in <root>/growth/channels.json so it can be exported and imported (hosted storage is temporary).
A legacy single `growth/profile.json` becomes the "default" channel the first time channels are read.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from studio.errors import StudioError
from studio.growth import channel_types, identity, store

NAME = "channels"
DEFAULT_ID = "default"
EXPORT_KIND = "yt-studio-channels"

DEFAULTS: dict = {
    "name": "My Channel",
    "type": channel_types.DEFAULT_TYPE,  # business | history | kids | general (see channel_types)
    "niche": "Business-model and economics explainers",
    "description": "",
    "language": "English",
    "audience": "Curious adults 18-44 who want to understand how companies make money",
    "posts_per_week": 2,
    "voice": "",  # edge-tts / ElevenLabs voice; empty = use TTS_VOICE from .env
    "renderer": "",  # 2d | blender; "" = RENDERER from .env
    "scene_style": "",  # 2d | 3d | mixed; "" = the channel type's default
    "music": "",  # generated | none; "" = automatic (your own track in assets/music wins)
    "music_mood": "",  # minor | major; "" = the channel type's default
    "tts_provider": "",  # edge | eleven | silent; "" = TTS_PROVIDER from .env
    "youtube_channel_id": "",  # empty = use CHANNEL_ID from .env
    "brand_primary": "#0B1F3A",
    "brand_accent": "#F5B700",
    "existing_videos": 0,
    "subscribers": 0,
    "watch_hours": 0.0,
    "newsletter_url": "",
    "affiliate_note": "",
    # identity (see studio/growth/identity.py): positioning, host character, look, playlists
    "niche_statement": "",  # one sentence: who it is for, what they get, what makes it different
    "tagline": "",
    "host_scenes": "auto",  # "auto": the mascot acts out some segments as a 3D host scene (3d/mixed style); "off"
    "mascot": {},  # name, kind, color, look, personality, catchphrase, intro_line, outro_line, on_thumbnail
    "theme": {},  # bg, accent, accent2, text, heading_font, intro_style, outro_style, thumbnail_style, motion
    "playlists": [],  # name, description, title_pattern, topics, youtube_id
}


def slug(name: str) -> str:
    """Stable id from a channel name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "channel"


def _clean(values: dict) -> dict:
    out = {k: values[k] for k in DEFAULTS if k in values and values[k] is not None}
    if "mascot" in out:
        out["mascot"] = identity.clean_mascot(out["mascot"])
    if "theme" in out:
        out["theme"] = identity.clean_theme(out["theme"])
    if "playlists" in out:
        out["playlists"] = identity.clean_playlists(out["playlists"])
    if "type" in out:
        out["type"] = channel_types.normalize(out["type"])
    for key, allowed in channel_types.CHOICES.items():
        if key in out:
            out[key] = str(out[key]).strip().lower()
            if out[key] not in allowed:
                names = ", ".join(a for a in allowed if a)
                raise StudioError(f"'{out[key]}' is not a valid {key}.",
                                  f"Choose one of: {names} (or leave it blank for the default).",
                                  f"Set {key} again.")
    return out


def _path(root: Path) -> Path:
    return store.global_file(root, NAME)


def _load(root: Path) -> dict:
    data = store.load(_path(root), None)
    if data is None:  # first use: migrate the old single profile, if any
        legacy = store.load(store.global_file(root, "profile"), {})
        data = {"active": DEFAULT_ID, "channels": {DEFAULT_ID: _clean(legacy)}}
    if not data.get("channels"):
        data["channels"] = {DEFAULT_ID: {}}
    if data.get("active") not in data["channels"]:
        data["active"] = next(iter(data["channels"]))
    return data


def _save(root: Path, data: dict) -> None:
    store.save(_path(root), data)


def _heal(values: dict) -> dict:
    """Replace a niche/audience that is another type's stock default with this type's own.

    Adding a kids channel copies the kids niche into it; switching its type to business used to keep that text, so
    topic suggestions stayed nursery rhymes. A stock default of a different type is never the owner's own text."""
    t = channel_types.info(values.get("type"))
    out = dict(values)
    for key in ("niche", "audience"):
        stock_other = {x[key] for k, x in channel_types.TYPES.items() if x is not t}
        stock_other.add(DEFAULTS[key])
        if out.get(key) in stock_other and out.get(key) != t[key]:
            out[key] = t[key]
    return out


def _full(values: dict) -> dict:
    full = copy.deepcopy({**DEFAULTS, **_clean(values)})
    return _heal(full)


def list_channels(root: Path) -> list[dict]:
    """Every channel as {id, active, **profile}."""
    d = _load(root)
    return [{"id": cid, "active": cid == d["active"], **_full(v)} for cid, v in d["channels"].items()]


def active_id(root: Path) -> str:
    return _load(root)["active"]


def get(root: Path, channel_id: str | None = None) -> dict:
    """A channel's full profile (the active one by default)."""
    d = _load(root)
    cid = channel_id or d["active"]
    if cid not in d["channels"]:
        raise StudioError(f"No channel '{cid}'.", f"Known channels: {', '.join(d['channels'])}.",
                          "Run `channels list` to see them, or `channels add` to create one.")
    return _full(d["channels"][cid])


def add(root: Path, name: str, activate: bool = True, **values) -> str:
    """Create a channel from a name plus any profile fields; returns its id."""
    if not name.strip():
        raise StudioError("A channel needs a name.", "The name was empty.",
                          "Pass a name, e.g. `channels add \"Money Maps\"`.")
    d = _load(root)
    base, cid, n = slug(name), slug(name), 2
    while cid in d["channels"]:
        cid, n = f"{base}-{n}", n + 1
    clean = _clean({**values, "name": name.strip()})
    t = channel_types.info(clean.get("type"))
    for key in ("niche", "audience"):  # a new channel starts from its type's defaults
        if not clean.get(key) or clean[key] == DEFAULTS[key]:
            clean[key] = t[key]
    d["channels"][cid] = clean
    if activate:
        d["active"] = cid
    _save(root, d)
    return cid


def update(root: Path, channel_id: str | None = None, **values) -> dict:
    """Change fields on a channel (the active one by default); unknown fields are ignored."""
    d = _load(root)
    cid = channel_id or d["active"]
    get(root, cid)
    d["channels"][cid] = _heal({**_full(d["channels"][cid]), **_clean(values)})
    _save(root, d)
    return _full(d["channels"][cid])


def switch(root: Path, channel_id: str) -> dict:
    """Make a channel the active one."""
    profile = get(root, channel_id)
    d = _load(root)
    d["active"] = channel_id
    _save(root, d)
    return profile


def remove(root: Path, channel_id: str) -> None:
    """Delete a channel profile (never the last one)."""
    d = _load(root)
    get(root, channel_id)
    if len(d["channels"]) == 1:
        raise StudioError("Cannot remove the only channel.", "At least one channel profile must exist.",
                          "Add another channel first, or edit this one instead.")
    del d["channels"][channel_id]
    if d["active"] == channel_id:
        d["active"] = next(iter(d["channels"]))
    _save(root, d)


def export_json(root: Path) -> str:
    """All channels as a JSON string to download and keep."""
    d = _load(root)
    return json.dumps({"kind": EXPORT_KIND, "version": 1, **d}, indent=2, ensure_ascii=False)


def import_json(root: Path, text: str, replace: bool = False) -> list[str]:
    """Add channels from an export. Existing ids are kept unless `replace`; returns the ids imported."""
    try:
        incoming = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StudioError("The channels file is not valid JSON.", str(exc),
                          "Use a file made by `channels export`.") from exc
    ok = isinstance(incoming, dict) and incoming.get("kind") == EXPORT_KIND
    if not ok or not isinstance(incoming.get("channels"), dict):
        raise StudioError("This is not a channels export.", "It is missing the expected header.",
                          "Use a file made by `channels export` or the app's Download button.")
    d = _load(root)
    done = []
    for cid, vals in incoming["channels"].items():
        if not isinstance(vals, dict) or (cid in d["channels"] and not replace):
            continue
        d["channels"][cid] = _clean(vals)
        done.append(cid)
    if incoming.get("active") in done:
        d["active"] = incoming["active"]
    _save(root, d)
    return done


def brief(root: Path) -> str | None:
    """Prompt brief for the active channel, or None while it is still the untouched default."""
    p = get(root)
    if (p["niche"] == DEFAULTS["niche"] and not p["description"] and p["name"] == DEFAULTS["name"]
            and p["type"] == DEFAULTS["type"]):
        return None
    return summary(p)


def summary(p: dict) -> str:
    """One paragraph for prompts."""
    text = (f"Channel '{p['name']}': {p['niche']}. Language: {p['language']}. Audience: {p['audience']}. "
            f"Posts {p['posts_per_week']} long video(s) per week. Faceless narration with charts and diagrams.")
    t = channel_types.info(p.get("type"))
    text += f" Format: {t['label']}. {t['guidance']}"
    text = f"{text} About: {p['description']}" if p.get("description") else text
    ident = identity.brief(p)
    return f"{text} {ident}" if ident else text


def type_info(root: Path, channel_id: str | None = None) -> dict:
    """The type definition (mode, made_for_kids, seeds...) of a channel; the active one by default."""
    return channel_types.info(get(root, channel_id)["type"])
