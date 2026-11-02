"""SEO pack: description, tags and chapters, with source lines and photo credits. Pure code, no LLM."""

from __future__ import annotations

from studio.growth import series as series_mod
from studio.growth.profile import load as load_profile
from studio.stages.review import build_description, chapters, disclaimer_for, fit_tags, mmss


def keywords_from(pkg: dict, title: str, extra: tuple[str, ...] = ("business model", "how it makes money",
                                                                  "economics explained")) -> list[str]:
    """Tags: the script's own tags first, then topic words and title phrases, de-duplicated."""
    seeds = list(pkg.get("tags") or []) + [pkg.get("topic", ""), title]
    words = [w.strip(".,:?!").lower() for w in (pkg.get("topic", "") + " " + title).split() if len(w) > 3]
    seen, out = set(), []
    for t in seeds + list(extra) + words:
        key = t.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(t.strip())
    return out


def build(root, pkg: dict, title: str, licences: list[dict], video_id: int | None = None,
          seg_seconds_key: str = "est_seconds") -> dict:
    """Return {description, tags, chapters, title}. Adds series, newsletter and affiliate lines when set."""
    profile = load_profile(root)
    chaps = chapters(pkg["segments"], float(pkg.get("build", {}).get("intro_seconds", 0)))
    from studio.growth import channels
    business = (channels.get(root).get("type") or "business") in ("business", "")
    desc = build_description(pkg, chaps, licences, disclaimer_for(root))
    extra = []
    pos = series_mod.position(root, video_id) if video_id is not None else None
    if pos:
        extra.append(series_mod.end_screen(*pos)["description_line"])
    if profile["newsletter_url"]:
        extra.append(f"Free weekly newsletter: {profile['newsletter_url']}")
    if profile["affiliate_note"]:
        extra.append(f"Links: {profile['affiliate_note']}\nSome links may be affiliate links; I may earn a "
                     "commission at no extra cost to you.")
    if extra:
        head, _, rest = desc.partition("\n\n")
        desc = "\n\n".join([head, "\n".join(extra), rest] if rest else [head, "\n".join(extra)])
    default_tags = ("business model", "how it makes money", "economics explained") if business else ()
    return {"title": title, "description": desc, "tags": fit_tags(keywords_from(pkg, title, default_tags)),
            "chapters": [f"{mmss(t)} {n}" for t, n in chaps], "chars": len(desc)}
