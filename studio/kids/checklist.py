"""Made for Kids checklist. Kids mode never uploads: the owner uploads by hand after these checks."""

from __future__ import annotations

import json
from pathlib import Path

from studio.kids import spec

# Manual items cannot be verified by code. Wording follows YouTube Help; re-read it before each upload
# because policies change: https://support.google.com/youtube/answer/9527654 (Made for Kids),
# https://support.google.com/youtube/answer/1311392 (monetisation: reused/mass-produced content).
MANUAL = [
    ("audience", "In YouTube Studio set audience to 'Yes, it's made for kids' for EVERY upload (legally required "
                 "for child-directed content; misrepresenting it can lead to enforcement)."),
    ("expectations", "Expect no comments, notifications, cards/end screens or personalised ads on Made for Kids "
                     "videos, and lower RPM than adult content. This is not a bug."),
    ("original", "Confirm the lyrics, melody, voice and art are yours or public domain. Do not reuse another "
                 "channel's songs, characters, thumbnails or titles."),
    ("music", "Use royalty-free or self-made music and keep the licence note. Modern arrangements of old "
              "rhymes are copyrighted even when the words are not."),
    ("variety", "Do not mass-produce near-identical videos. Vary songs, scenes and teaching goals; add real "
                "creative input per video. YouTube demonetises repetitive/inauthentic content."),
    ("safety", "Watch the whole video: no scary, violent or unsafe moments; no calls to buy, click or subscribe "
               "aimed at children; no children's personal data; no clickbait metadata."),
    ("disclosure", "Tick 'altered or synthetic content' disclosure if the narration is a realistic synthetic "
                   "voice, per YouTube's current rules."),
    ("review", "A parent or caregiver has watched it once and is happy to show it to a child."),
]


def auto_checks(data: dict, has_video: bool, has_thumb: bool) -> list[dict]:
    """Checks the code can do for itself."""
    problems = spec.validate(data)
    chorus = [s for s in data.get("scenes", []) if s.get("kind") == "chorus"]
    return [
        {"id": "script_valid", "ok": not problems, "note": "; ".join(problems) or "script passes validation"},
        {"id": "no_franchise_names", "ok": not any("franchises" in p for p in problems),
         "note": "no reference to existing kids' brands"},
        {"id": "source_declared", "ok": data.get("source") in spec.SOURCES, "note": f"source={data.get('source')}"},
        {"id": "repeated_chorus", "ok": len(chorus) >= 2, "note": f"{len(chorus)} chorus scenes"},
        {"id": "video_built", "ok": has_video, "note": "final.mp4 exists"},
        {"id": "thumbnail_built", "ok": has_thumb, "note": "thumbnail.jpg exists"},
    ]


def run(project: Path) -> dict:
    """Write and return made_for_kids_checklist.json for a kids project folder."""
    data = json.loads((project / "script.json").read_text(encoding="utf-8"))
    auto = auto_checks(data, (project / "final.mp4").exists(), (project / "thumbnail.jpg").exists())
    result = {"title": data["title"], "auto": auto,
              "manual": [{"id": k, "text": t, "done": False} for k, t in MANUAL],
              "ready_to_upload": all(a["ok"] for a in auto)}
    (project / "made_for_kids_checklist.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def render_text(result: dict) -> str:
    """Terminal-friendly view of the checklist."""
    lines = [f"Made for Kids checklist: {result['title']}", "", "Automatic checks:"]
    lines += [f"  [{'x' if a['ok'] else ' '}] {a['id']}: {a['note']}" for a in result["auto"]]
    lines += ["", "You must confirm by hand before uploading:"]
    lines += [f"  [ ] {m['text']}" for m in result["manual"]]
    lines += ["", "Kids mode never uploads or publishes. Upload the MP4 yourself in YouTube Studio."]
    return "\n".join(lines)
