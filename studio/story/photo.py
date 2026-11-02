"""On-demand photo scenes: the script asks for a real photo only where one truly helps.

A segment opts in with `photo`: {"subject": "what the photo shows", "caption": "short label", "layout": "full|inset"}.
No `photo` key means no photo; there is no default and no photo backdrop.
"""

from __future__ import annotations

LAYOUTS = ("full", "inset")
MAX_PHOTOS = 3
MAX_CAPTION_WORDS = 8

PROMPT_RULE = (
    "- `photo` is OPTIONAL and rare: add it to a segment only when a real photograph of a real person, place or "
    "object is needed to understand the line (a named building, a coin, a ruin, a real animal). Never for ideas, "
    "numbers, maps, charts or scenes the cast acts out. At most {max} per video, never in two segments in a row, "
    'and none in the hook. Shape: "photo": {{"subject": "the concrete thing to find, 2-6 words", "caption": '
    '"a label of at most 8 words", "layout": "full or inset"}}. Leave the key out everywhere else.')


PACK_HINT = {
    "history": " Good: a real ruin, coin, statue or landscape the narration names. Never a battle or a person's face.",
    "kids": " Good: a real animal or everyday object the child is learning about. Never a photo of a person or child.",
    "general": " Good: a real company site, product or place the narration names. Never generic money shots.",
}


def prompt_rule(pack: str = "general") -> str:
    """The paragraph inserted into the script prompt of every pack (`pack` adds that channel type's guidance)."""
    return PROMPT_RULE.format(max=MAX_PHOTOS) + PACK_HINT.get(pack, "")


def request(seg: dict) -> dict | None:
    """The segment's photo request with defaults filled in, or None when it asks for none."""
    p = seg.get("photo")
    if not isinstance(p, dict) or not str(p.get("subject") or "").strip():
        return None
    layout = p.get("layout") if p.get("layout") in LAYOUTS else "inset"
    return {"subject": str(p["subject"]).strip(), "caption": str(p.get("caption") or "").strip(), "layout": layout}


def photo_problems(segs: list[dict]) -> list[str]:
    """Plain-language problems with the optional `photo` keys (empty when none are used or all are fine)."""
    out: list[str] = []
    n, prev = 0, False
    for i, s in enumerate(segs, 1):
        if "photo" not in s or s["photo"] in (None, False):
            prev = False
            continue
        p = s["photo"]
        if not isinstance(p, dict) or not str(p.get("subject") or "").strip():
            out.append(f"segment {i}: photo needs a `subject` (what real thing the photo shows)")
            prev = False
            continue
        n += 1
        if p.get("layout") not in (None, *LAYOUTS):
            out.append(f"segment {i}: photo layout {p['layout']!r} is not one of {list(LAYOUTS)}")
        if len(str(p.get("caption") or "").split()) > MAX_CAPTION_WORDS:
            out.append(f"segment {i}: photo caption is longer than {MAX_CAPTION_WORDS} words")
        if i == 1:
            out.append("segment 1: no photo in the hook; open on the story")
        if prev:
            out.append(f"segment {i}: photos in two segments in a row; keep them apart")
        prev = True
    if n > MAX_PHOTOS:
        out.append(f"{n} photo scenes; keep it to {MAX_PHOTOS} at most (photos only where the script needs one)")
    return out
