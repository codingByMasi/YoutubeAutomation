"""Visual planning helpers: queries from visual_intent, shot-type rule, footage reuse ledger, semantic ranking."""

from __future__ import annotations

import re
from pathlib import Path

from studio.growth import store

SHOT_TYPES = ("wide", "close", "detail", "map", "chart", "text")
LEDGER = "footage_ledger"


def queries_for(seg: dict) -> list[str]:
    """Stock search terms: must_show first, then visual_keywords, minus anything in `avoid`."""
    vi = seg.get("visual_intent") or {}
    avoid = {w for w in re.findall(r"[a-z]+", str(vi.get("avoid", "")).lower()) if len(w) > 3}
    must = str(vi.get("must_show") or "").strip()
    terms = ([must] if must else []) + list(seg.get("visual_keywords") or [])
    kept = [t for t in terms if not avoid & set(re.findall(r"[a-z]+", t.lower()))]
    return kept or list(seg.get("visual_keywords") or []) or terms


def shot_problems(segs: list[dict]) -> list[str]:
    """No three consecutive segments with the same shot_type; shot_type must be a known value."""
    out, run = [], 1
    for i, s in enumerate(segs, 1):
        t = (s.get("visual_intent") or {}).get("shot_type")
        if t is not None and t not in SHOT_TYPES:
            out.append(f"segment {i}: shot_type {t!r} not in {list(SHOT_TYPES)}")
        prev = (segs[i - 2].get("visual_intent") or {}).get("shot_type") if i > 1 else None
        run = run + 1 if t and t == prev else 1
        if run >= 3:
            out.append(f"segments {i - 2}-{i}: three {t!r} shots in a row; change one to a different shot_type")
    return out


# ---------- footage reuse ledger ----------
def _path(root: Path) -> Path:
    return store.channel_file(root, LEDGER)


def recent_assets(root: Path, n: int = 3, exclude_video: int | None = None) -> set[str]:
    """Asset ids (page urls) used by the channel's last n videos."""
    d = store.load(_path(root), {})
    vids = [k for k in sorted(d, key=int) if int(k) != exclude_video][-n:]
    return {a for k in vids for a in d[k]}


def record_assets(root: Path, video_id: int, assets: list[str]) -> None:
    d = store.load(_path(root), {})
    d[str(video_id)] = sorted(set(assets))
    keep = sorted(d, key=int)[-30:]
    store.save(_path(root), {k: d[k] for k in keep})


# ---------- semantic relevance (optional) ----------
class SemanticScorer:
    """Scores (text, image) candidates against narration + must_show. None from `make_scorer` means not available."""

    def __init__(self, st_model=None, clip=None) -> None:
        self.st, self.clip = st_model, clip

    def score(self, query: str, candidate_text: str, image: Path | None = None) -> float:
        if self.clip is not None and image is not None and image.exists():
            return float(self.clip(query, image))
        if self.st is not None:
            a, b = self.st.encode([query, candidate_text], normalize_embeddings=True)
            return float((a * b).sum())
        return 0.0


def make_scorer() -> SemanticScorer | None:
    """open_clip (images) or sentence-transformers (text) if installed; otherwise None (tag-overlap stays)."""
    try:
        from sentence_transformers import SentenceTransformer
        return SemanticScorer(st_model=SentenceTransformer("all-MiniLM-L6-v2"))
    except Exception:  # noqa: BLE001 - optional dependency: missing, offline, or no model download
        return None


def best_candidate(scorer: SemanticScorer | None, query: str, clips: list) -> object | None:
    """The candidate with the highest semantic score (page_url slug as text); first one without a scorer."""
    if not clips:
        return None
    if scorer is None:
        return clips[0]
    def txt(c) -> str:
        return re.sub(r"[-_/]+", " ", str(getattr(c, "page_url", "")).rsplit("//", 1)[-1])
    return max(clips, key=lambda c: scorer.score(query, txt(c), getattr(c, "path", None)))
