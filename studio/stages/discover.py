"""Topic discovery without a seed: dedupe, channel-fit filtering, auto-suggest, and a Claude prompt route.

Research only finds topics. Nothing here copies another creator's content.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Callable
from datetime import UTC, datetime

from studio.context import Ctx
from studio.errors import StudioError
from studio.models import Idea
from studio.util.logging import get_logger

log = get_logger("discover")

AUTO_SEED = "auto"
SKIP_WORDS = set("a an the of to in on for and or how why what is are does do did can with my your their its".split())
# Off-channel: games, pay/jobs, how-to-hustle and clickbait. The channel explains business models.
BLOCKED = {
    "simulator", "tycoon", "roblox", "minecraft", "gta", "game", "games", "gameplay", "mod", "mods", "cheat",
    "hack", "free", "salary", "salaries", "pay", "paid", "employee", "employees", "job", "jobs", "hiring",
    "career", "careers", "interview", "crew", "worker", "workers", "wage", "wages", "income", "app", "apk",
    "download", "reddit", "movie", "song", "lyrics", "meme", "sims",
}
FIT_WORDS = {"money", "profit", "profits", "business", "economics", "revenue", "earn", "earns", "makes", "make",
             "model", "billion", "cost", "price", "pricing", "work", "works", "failed", "collapse", "rich",
             "worth", "valuation", "scam", "trap", "margin", "subsidy", "monopoly"}
# Subjects for hands-off suggestions: business-model explainers, India and global.
SUBJECTS = [
    "Zomato", "Swiggy", "Jio", "Flipkart", "Paytm", "Ola", "Dream11", "IRCTC", "Indian Railways", "Amul",
    "Nykaa", "Lenskart", "Zerodha", "PhonePe", "Byju's", "Tata Motors", "IndiGo", "Air India", "Reliance Retail",
    "Netflix", "Spotify", "Uber", "Airbnb", "Amazon Prime", "Costco", "IKEA", "Starbucks", "McDonald's",
    "Disney", "Tesla", "Apple", "Visa", "Ryanair", "airlines", "cruise lines", "casinos", "Las Vegas hotels",
    "Ticketmaster", "Shein", "Temu", "Dollar General", "Trader Joe's", "Aldi", "Lululemon", "Rolex",
    "Formula 1", "the NFL", "the IPL", "Walmart", "Nvidia", "private jets", "fast fashion", "luxury brands",
    "supermarkets", "movie theaters", "theme parks", "banks", "insurance companies", "credit cards",
]
ANGLES = ("how {s} makes money", "why {s} is so cheap", "how {s} really works", "{s} business model")


def _stem(w: str) -> str:
    for suf in ("ing", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def key_tokens(text: str) -> frozenset[str]:
    """Meaning of a topic with filler words and plurals removed, so near-duplicates compare equal."""
    return frozenset(_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in SKIP_WORDS and len(w) > 1)


def is_duplicate(topic: str, others: list[frozenset[str]]) -> bool:
    """True if `topic` says the same as a known one (same words, or one adds at most one extra word)."""
    t = key_tokens(topic)
    if not t:
        return True
    return any(t == o or (min(len(t), len(o)) >= 2 and (t <= o or o <= t) and abs(len(t) - len(o)) <= 1)
               for o in others)


def off_channel(topic: str) -> bool:
    """True for topics the channel would not make (games, salaries, jobs, downloads...)."""
    words = set(re.findall(r"[a-z0-9]+", topic.lower()))
    return bool(words & BLOCKED)


def fits_channel(topic: str, seed: str = "") -> bool:
    """On-channel if not blocked and it talks about money/business, or shares words with the seed."""
    if off_channel(topic):
        return False
    words = set(re.findall(r"[a-z0-9]+", topic.lower()))
    return bool(words & FIT_WORDS) or bool(seed and key_tokens(seed) & key_tokens(topic))


def clean_topics(topics: list[str], seed: str = "", known: list[str] | None = None) -> list[str]:
    """Drop off-channel topics and near-duplicates (also against `known`), keeping the first of each group."""
    seen = [key_tokens(k) for k in (known or [])]
    out: list[str] = []
    for t in topics:
        t = t.strip()
        if not t or not fits_channel(t, seed) or is_duplicate(t, seen):
            continue
        seen.append(key_tokens(t))
        out.append(t)
    return out


def known_topics(ctx: Ctx) -> list[str]:
    """Every topic ever saved, so nothing is suggested twice."""
    return [i.topic for i in ctx.session.query(Idea).filter(Idea.seed != "__demo__").all()]


def _demand(position: int, total: int) -> float:
    """0-10 from how high YouTube's own search box ranks the phrase (top result = 10)."""
    return round(10 * (1 - position / max(total, 1)), 1)


def auto_suggest(ctx: Ctx, count: int = 8, suggest: Callable[[str], list[str]] | None = None,
                 rng: random.Random | None = None) -> list[Idea]:
    """Pick fresh subjects, ask YouTube search suggestions how people phrase them, save the best new topics."""
    from studio.stages.research import fetch_suggestions

    suggest = suggest or fetch_suggestions
    rng = rng or random.Random(datetime.now(UTC).strftime("%Y%m%d%H%M%S"))
    known = known_topics(ctx)
    used = " ".join(known).lower()
    fresh = [s for s in SUBJECTS if s.lower() not in used] or SUBJECTS[:]
    rng.shuffle(fresh)
    found: list[tuple[str, float]] = []
    for subject in fresh[: count + 4]:
        angle = rng.choice(ANGLES).format(s=subject)
        try:
            sug = suggest(angle)
        except Exception as exc:  # noqa: BLE001 - best effort
            log.warning("Suggestions unavailable for %r: %s", angle, exc)
            sug = []
        pool = clean_topics([s for s in sug if key_tokens(subject) & key_tokens(s)], angle, known)
        pick = pool[0] if pool else None
        if pick is None and not sug:
            pick = angle  # offline: the plain template, unranked
        if pick and not is_duplicate(pick, [key_tokens(k) for k in known] + [key_tokens(f[0]) for f in found]):
            rank = sug.index(pick) if pick in sug else len(sug)
            found.append((pick, _demand(rank, max(len(sug), 4)) if sug else 3.0))
        if len(found) >= count:
            break
    if not found:
        raise StudioError("No new topic ideas were found.", "Search suggestions returned nothing new.",
                          "Try again later, type a seed idea, or use the 'Ask Claude for ideas' option.")
    ideas = [Idea(seed=AUTO_SEED, topic=t, demand_score=d) for t, d in found]
    ctx.session.add_all(ideas)
    ctx.session.commit()
    return ideas


def ideas_prompt(ctx: Ctx, count: int = 10) -> str:
    """Text to paste into Claude (claude.ai or Claude Code) asking for new channel-fit topics."""
    avoid = "\n".join(f"- {t}" for t in known_topics(ctx)[-60:]) or "- (none yet)"
    return f"""You are the topic researcher for a faceless YouTube channel that explains business models and
economics in English with charts and diagrams. Every figure in a video needs a public source.

Suggest {count} NEW video topics. Mix Indian and global companies and industries. Prefer the shapes
"How X really makes money", "Why X is so cheap/expensive", "The economics of X", "Why X failed".
Pick topics people search for and that can be explained with real, citable numbers. Search the web to check
the topic is real and current. Do not copy any creator's video; topics only.

Do NOT suggest these (already used or saved) or close variations of them:
{avoid}

Answer with ONLY this JSON, nothing else:
{{"topics": [{{"topic": "How Zomato really makes money", "why": "one short sentence on why it will get views"}}]}}
"""


def import_ideas(ctx: Ctx, text: str) -> list[Idea]:
    """Parse Claude's answer (JSON, or one topic per line) and save the new, on-channel, non-duplicate ones."""
    text = text.strip()
    if not text:
        raise StudioError("Nothing was pasted.", "", "Paste Claude's answer into the box and try again.")
    topics: list[str] = []
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            items = data.get("topics", []) if isinstance(data, dict) else data
            topics = [(x.get("topic", "") if isinstance(x, dict) else str(x)) for x in items]
        except (ValueError, AttributeError) as exc:
            raise StudioError("The pasted answer is not valid JSON.", str(exc),
                              "Paste Claude's whole answer, or one topic per line.") from exc
    else:
        topics = [re.sub(r"^[\s\-*\d.)]+", "", ln) for ln in text.splitlines()]
    fresh = [t for t in topics if t.strip() and not off_channel(t)]
    kept = clean_topics_loose(fresh, known_topics(ctx))
    if not kept:
        raise StudioError("No new topics were found in the answer.", "They were empty, off-channel or already saved.",
                          "Ask Claude again, or type your own topic.")
    ideas = [Idea(seed="claude", topic=t, demand_score=5.0) for t in kept]
    ctx.session.add_all(ideas)
    ctx.session.commit()
    return ideas


def clean_topics_loose(topics: list[str], known: list[str]) -> list[str]:
    """Like clean_topics but trusts the source for channel fit (only blocks junk and duplicates)."""
    seen = [key_tokens(k) for k in known]
    out = []
    for t in topics:
        t = t.strip()
        if t and not is_duplicate(t, seen):
            seen.append(key_tokens(t))
            out.append(t)
    return out
