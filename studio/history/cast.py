"""The history channel's scene rules and prompt block. No fixed cast and no shared character template: every
character is drawn from the script's own description by `studio.history.figures`. Everything here is original."""

from __future__ import annotations

from studio.history import wardrobe

SCENE_TYPES = ("skit", "map", "diagram", "easel", "archive", "calendar", "silhouette", "title")
LEGACY_SCENES = ("lectern",)  # older scripts: drawn as a plain title card now (the host is gone)
MAX_SPEECH_LINES = 6
MAX_SPEECH_WORDS = 12

# No fixed cast: every character comes from the script's own descriptions (see `studio.history.figures`).
# A name nobody described is drawn from its own words, never mapped to a recurring character.
GENERIC = "Bystander"  # stand-in name when a scene needs someone and the script names nobody

# Faction colours for map flags and crowds (one colour per side, kept for the whole video).
FACTION_COLORS = ["#C0392B", "#2471A3", "#1E8449", "#B7950B", "#7D3C98", "#CA6F1E", "#117A65", "#566573"]


def faction_color(index: int) -> str:
    """Colour for the n-th faction of a video (wraps)."""
    return FACTION_COLORS[index % len(FACTION_COLORS)]


def prompt_block(profile: dict) -> str:
    """Cast and depiction rules for the planner and script prompts ('' when the profile has no cast)."""
    dep = profile.get("depiction")
    if not profile.get("cast") or not dep:
        return ""
    lines = ["# Cast and depiction (original characters only; never imitate any other channel's characters)",
             "Invent the cast the story needs: every character in the script gets a short visual description "
             "(role, age, gender, era costume, face traits) so a soldier looks like a soldier and women look like "
             "women, dressed for the era and place; use as many characters as the story calls for. 2D or 3D follows "
             "the script. There is no fixed or recurring cast and no host: every character is one the story "
             "itself needs, named and described from the story."]
    lines.append("Historical figures: never a real likeness. Each one keeps the same described look for the whole "
                 "video (its own face, build, clothes, headwear and props), written fresh for THIS story and the "
                 "role the person plays in it (age, rank and costume of that moment); never reuse a description "
                 "from another video, and give every character a different face. Rules:")
    lines += [f"- {r}" for r in dep.get("rules", [])]
    lines.append(wardrobe.prompt_line())
    lines.append(f"Scene types per segment: {', '.join(SCENE_TYPES)}. Add optional keys to each segment: `scene`, "
                 "`cast` (the story's own character names), `staging` (one sentence), `speech` (at most "
                 f"{MAX_SPEECH_LINES} on-screen lines of at most {MAX_SPEECH_WORDS} words, each "
                 '{"who": "...", "text": "..."}). Speech is invented dialogue: use it only for tone, never for quotes '
                 "you present as real; real quotes go in the narration.")
    return "\n".join(lines)


def scene_problems(pkg: dict, profile: dict | None = None) -> list[str]:
    """Plain-language problems with the optional scene/cast/speech keys of each segment."""
    out: list[str] = []
    if pkg.get("era") and not wardrobe.known(str(pkg["era"]).lower()):
        out.append(f"era {pkg['era']!r} is not one of {[wardrobe.DEFAULT, *wardrobe.ERAS]}")
    run, prev = 0, None
    for i, s in enumerate(pkg.get("segments") or [], 1):
        scene = s.get("scene")
        if scene is None:
            run, prev = 0, None
            continue
        if scene not in (*SCENE_TYPES, *LEGACY_SCENES):
            out.append(f"segment {i}: scene {scene!r} is not one of {list(SCENE_TYPES)}")
        if s.get("era") and not wardrobe.known(str(s["era"]).lower()):
            out.append(f"segment {i}: era {s['era']!r} is not one of {[wardrobe.DEFAULT, *wardrobe.ERAS]}")
        run = run + 1 if scene == prev else 1
        prev = scene
        if run >= 3 and scene not in ("map", "diagram"):
            out.append(f"segments {i - 2}-{i}: three {scene!r} scenes in a row; change one to a different scene type")
        speech = s.get("speech") or []
        if scene != "skit" and speech:
            out.append(f"segment {i}: speech lines only belong to a 'skit' scene")
        if len(speech) > MAX_SPEECH_LINES:
            out.append(f"segment {i}: {len(speech)} speech lines; keep it to {MAX_SPEECH_LINES}")
        for line in speech:
            n = len(str(line.get("text", "")).split()) if isinstance(line, dict) else 99
            if n > MAX_SPEECH_WORDS:
                out.append(f"segment {i}: a speech line has {n} words; keep each under {MAX_SPEECH_WORDS + 1}")
        if scene in ("title", "calendar", "easel", "silhouette", "archive") and float(s.get("est_seconds") or 0) > 6.0:
            secs = float(s["est_seconds"])
            out.append(f"segment {i}: a {scene} card would hold the screen for about {secs:.0f} s; keep "
                       "it to 6 s (about 15 words) or use a skit, map or diagram scene")
        if scene == "skit" and not (s.get("cast") or []):
            out.append(f"segment {i}: a skit needs `cast` (at least one character)")
    return out
