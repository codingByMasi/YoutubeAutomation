"""Automatic checks of the drawn cast scenes, for any story: say what is wrong and in which segment.

Every cast scene is drawn by code, so it can be checked by code. For each segment this draws a few frames and flags:
- text that runs past the picture edge (a long title, a map name at the border);
- two pieces of text drawn on top of each other (map names, labels);
- a skit backdrop that does not fit the place the script describes (sea with no sea in the setting, an unknown name);
- a figure whose mouth moves to the narration instead of to its own skit line.
`check_package` runs inside `qa`, so `build` prints the result for every video.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path

from PIL import ImageDraw

from studio.history import render as R

MARGIN = 2  # pixels a text may touch the picture edge
OVERLAP = 0.2  # share of the smaller text box that may be covered by another text
_GROUPS = {name: words for name, words in R._BACK_WORDS}  # backdrop -> the words that call for it
_PLACE_ONLY = ("sea", "snow", "desert", "mountains")  # backdrops that are wrong anywhere else


@contextmanager
def record_text():
    """Collect (text, box) for every text drawn with Pillow while the block runs."""
    items: list[tuple[str, tuple[float, float, float, float]]] = []
    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *args, **kwargs):
        try:
            if self._image.size != (R.W, R.H):
                return original(self, xy, text, *args, **kwargs)  # a figure's own badge, not scene text
            box = self.textbbox(xy, str(text), font=kwargs.get("font"), anchor=kwargs.get("anchor"),
                                stroke_width=kwargs.get("stroke_width", 0))
            items.append((str(text), box))
        except Exception:  # noqa: BLE001 - a text we cannot measure is simply not checked
            pass
        return original(self, xy, text, *args, **kwargs)

    ImageDraw.ImageDraw.text = spy
    try:
        yield items
    finally:
        ImageDraw.ImageDraw.text = original


def text_problems(items: list[tuple[str, tuple]], width: int = R.W, height: int = R.H, zoom: float = 1.0) -> list[str]:
    """Texts cut off by the picture edge (as seen after the camera zooms in), and texts drawn over each other."""
    out: list[str] = []
    ix, iy = width * (1 - 1 / zoom) / 2, height * (1 - 1 / zoom) / 2
    for text, (x0, y0, x1, y1) in items:
        if x0 < ix - MARGIN or y0 < iy - MARGIN or x1 > width - ix + MARGIN or y1 > height - iy + MARGIN:
            out.append(f"the text {text[:40]!r} runs past the edge of the picture")
    seen: set[tuple] = set()
    for i, (ta, a) in enumerate(items):
        for tb, b in items[i + 1:]:
            if ta == tb and a == b:
                continue  # the same text drawn twice (shadow)
            w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
            small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if w > 0 and h > 0 and small > 0 and w * h / small > OVERLAP and (ta, tb) not in seen:
                seen.add((ta, tb))
                out.append(f"the texts {ta[:30]!r} and {tb[:30]!r} overlap")
    return out


def diagram_problems(seg: dict, items: list[tuple[str, tuple]]) -> list[str]:
    """Every word of every step must be drawn, and inside its own box."""
    if seg.get("scene") != "diagram":
        return []
    from studio.history import autoscene
    steps = autoscene.steps_for(str(seg.get("narration", "")), (seg.get("scene_data") or {}).get("steps")) or []
    if not steps:
        return []
    cw, x0 = R.diagram_layout(len(steps))
    drawn = " ".join(t for t, _ in items).lower().split()
    out: list[str] = []
    for k, step in enumerate(steps):
        lo, hi = x0 + k * (cw + 60), x0 + k * (cw + 60) + cw
        missing = [w for w in step.lower().split() if w not in drawn]
        if missing:
            out.append(f"step {k + 1} is cut short: {', '.join(missing[:3])!r} is not shown")
        for text, (a, _, b, _) in items:
            if text in step and lo - 6 <= (a + b) / 2 <= hi + 6 and (a < lo + 4 or b > hi - 4) and len(text) > 2:
                out.append(f"step {k + 1}: the text {text[:30]!r} touches or crosses the edge of its box")
    return out


def backdrop_problems(seg: dict) -> list[str]:
    """A skit backdrop that contradicts the place the script describes."""
    if seg.get("scene") != "skit":
        return []
    given = str((seg.get("scene_data") or {}).get("backdrop") or "").lower()
    setting = R.setting_words(seg).lower()
    if given and given not in R.BACKDROPS:
        return [f"backdrop {given!r} is not one of {', '.join(R.BACKDROPS)}"]
    shown = given or R.guess_backdrop(setting) or R.DEFAULT_BACKDROP["skit"]
    if shown in _PLACE_ONLY:
        hits = sum(len(re.findall(r"\b" + w + r"s?\b", setting)) for w in _GROUPS.get(shown, ()))
        if not hits:
            return [f"the backdrop is {shown!r} but nothing in the scene's setting says so"]
    guess = R.guess_backdrop(setting)
    if given and guess and guess != given and guess in _PLACE_ONLY:
        return [f"the backdrop is {given!r} but the setting suggests {guess!r}"]
    return []


def mouth_problems(seg: dict, dur: float, cast: R.Cast) -> list[str]:
    """A figure's mouth must follow only its own skit line, never the narration."""
    n = int(dur * R.FPS) + 2
    loud = R.Scene(seg, dur, cast, [1.0] * n, 0)
    quiet = R.Scene(seg, dur, cast, [0.0] * n, 0)
    first = loud.starts[0] if loud.starts else dur
    t = min(dur * 0.5, max(0.3, first - 0.4))  # narration only: no skit line is being spoken yet
    if loud.frame(t).tobytes() != quiet.frame(t).tobytes():
        return ["a figure's mouth moves to the narration instead of to its own line"]
    return []


STILL_SECONDS = 5.0  # a picture may not hold still longer than this
STILL_DIFF = 0.6  # mean change (0-255) between two samples half a second apart that counts as "nothing moved"


def _view(scene: R.Scene, t: float):
    """The picture as the viewer sees it at second t (after the camera), small and grey."""
    import numpy as np
    from PIL import Image
    img = scene.frame(t)
    z, fx, fy = scene.camera(t)
    cw, ch = R.W / max(z, 1.0), R.H / max(z, 1.0)
    x0, y0 = min(max(fx * R.W - cw / 2, 0), R.W - cw), min(max(fy * R.H - ch / 2, 0), R.H - ch)
    return np.asarray(img.resize((128, 72), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)).convert("L"), dtype=float)


def still_problems(scene: R.Scene, dur: float) -> list[str]:
    """Stretches where the picture does not change at all for `STILL_SECONDS` or more."""
    import numpy as np
    times = [k * 0.5 for k in range(int(dur * 2))]
    frames = [_view(scene, t) for t in times]
    run = 0.0
    for a, b, t in zip(frames, frames[1:], times[1:]):
        run = run + 0.5 if float(np.abs(a - b).mean()) < STILL_DIFF else 0.0
        if run >= STILL_SECONDS:
            return [f"the picture holds still for {run:.0f}+ s around {t:.0f}s: add movement (a cut, an action, "
                    "a reveal) or shorten the scene"]
    return []


def check_package(pkg: dict) -> list[str]:
    """Plain-language problems found in the drawn scenes of a script package (empty when all is well)."""
    segs = pkg.get("segments") or []
    if not any(isinstance(s, dict) and s.get("scene") for s in segs):
        return []
    cast = R.Cast(Path("."), pkg.get("characters"))
    out: list[str] = []
    for pos, seg in enumerate(segs, 1):
        if not isinstance(seg, dict) or not seg.get("scene"):
            continue
        dur = float(seg.get("real_seconds") or seg.get("est_seconds") or 6.0)
        where = f"Segment {pos} ({seg['scene']}, {str(seg.get('chapter') or '')[:30]})"
        found = backdrop_problems(seg)
        try:
            scene = R.Scene({**seg, "era": seg.get("era") or "default"}, dur, cast, [0.0] * (int(dur * R.FPS) + 2), 0)
            for t in (dur * 0.5, dur * 0.9):  # each frame on its own: a text may legitimately move
                with record_text() as items:
                    scene.frame(t)
                more = diagram_problems(seg, items) if t == dur * 0.9 else []  # all steps are on screen by then
                zoom = R.MAX_ZOOM.get(seg["scene"], R.DEFAULT_MAX_ZOOM) if seg["scene"] != "skit" else 1.0
                found += [p for p in text_problems(items, zoom=zoom) + more if p not in found]
            found += mouth_problems({**seg, "era": seg.get("era") or "default"}, dur, cast)
            found += still_problems(scene, dur)
        except Exception as exc:  # noqa: BLE001 - a check must never stop a build
            found.append(f"could not be checked ({str(exc)[:80]})")
        out += [f"{where}: {f}" for f in found]
    return out
