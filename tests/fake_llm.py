"""Deterministic fake LLM: builds canned, rule-passing answers for the three story tasks of any channel pack.

No network and no real model. `write_plan/write_script/write_review` put the JSON where `ask_json` expects it
(projects/<id>/prompts/<task>.response.json), exactly as a Claude Code session would after answering a prompt file.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from studio.story import profile as sp

SHAPES = {  # pack -> (beats, seconds per beat, hook seconds)
    "explainer": (18, 28, 12), "general": (16, 28, 12), "history": (18, 30, 14), "kids": (10, 18, 8)}
LENGTHS = [4, 14, 6, 16, 9, 12, 5, 17, 8, 13]  # sentence lengths: a varied rhythm
WORDS = ("shop pay milk rent cost cup sell buy tea farm bean price rise fall plan map port ship coin salt wind "
         "road town bell door light stone river field cart wheel bread").split()
KIDS_WORDS = "pip duck ball red hop run sun fun big small yes look see find kind mud pond wave".split()


def _sentence(n: int, k: int, kids: bool) -> str:
    pool = KIDS_WORDS if kids else WORDS
    words = [pool[(k * 7 + i * 3) % len(pool)] for i in range(n)]
    words[0] = words[0].capitalize()
    return " ".join(words) + "."


def narration(words: int, seed: int, kids: bool = False, cap: int = 18) -> str:
    out, total, i = [], 0, 0
    lengths = [min(x, cap) for x in LENGTHS] if not kids else [3, 6, 4, 7, 5]
    while total < words:
        n = min(lengths[(seed + i) % len(lengths)], words - total) if words - total >= 3 else words - total
        if n < 1:
            break
        out.append(_sentence(n, seed * 11 + i * 5, kids))
        total += n
        i += 1
    return " ".join(out)


def facts() -> list[dict]:
    return [{"id": f"f{i}", "claim": f"Claim number {i} about the topic", "figure": fig, "unit": "billion USD",
             "year": 2024, "source_url": f"https://example.org/report{i}",
             "quote_snippet": f"the company reported {fig} billion in 2024", "is_estimate": False}
            for i, fig in enumerate((1.2, 3.4, 5.6, 7.8, 9.9), 1)]


def fake_fetch(url: str) -> tuple[int, str]:
    """Pretend web: every example.org report page contains its figure."""
    i = int(url.rsplit("report", 1)[-1])
    fig = (1.2, 3.4, 5.6, 7.8, 9.9)[i - 1]
    return 200, f"Annual summary. In 2024 the company reported {fig} billion in sales, up from last year."


def plan(pack: str) -> dict:
    beats_n, sec, hook_s = SHAPES[pack]
    kids = pack == "kids"
    devices = ["question", "reveal", "example", "pattern_break"]
    beats = []
    for n in range(1, beats_n + 1):
        beats.append({"n": n, "chapter": f"Chapter {(n - 1) // 3 + 1}", "purpose": "move the story", "seconds":
                      hook_s if n == 1 else sec, "device": devices[(n - 1) % len(devices)],
                      "key_fact": f"fact {n % 5 + 1}", "fact_ids": [f"f{n % 5 + 1}"],
                      "emotion": "hook" if n == 1 else "tense" if n % 4 == 0 else "neutral"})
    loops = ([{"id": "L1", "question": "Where does the money go?", "plant": 1, "payoff": 6},
              {"id": "L2", "question": "Who pays in the end?", "plant": 2, "payoff": 8},
              {"id": "L3", "question": "What breaks first?", "plant": 6, "payoff": 11},
              {"id": "L4", "question": "What stays hidden?", "plant": 9, "payoff": 15}] if not kids else
             [{"id": "L1", "question": "Where is the ball?", "plant": 1, "payoff": 8}])
    types = sp.get(pack)["hook_formulas"]
    hooks = []
    for i in range(8):
        t = types[i % len(types)]
        hooks.append({"hook_type": t, "line": f"Why does variant {chr(65 + i)} cost four times more? Find out at the end."
                      if not kids else f"Look, it is Pip! Where is the ball {i}?", "why": "curiosity gap",
                      "score": {"curiosity": 3 + i % 3, "clarity": 4, "stakes": 3 + i % 2, "promise": 4}})
    return {"facts": facts() if not kids else facts()[:4],
            "outline": {"audience_question": "Why?", "big_idea": "It is rent.", "promise": "You will know.",
                        "title_promise": "How the shop really works", "arc": f"{pack}-arc-a", "beats": beats,
                        "loops": loops, "ending": {"callback": "back to the start", "takeaway": "Rent wins.",
                                                   "cta_question": "What would you cut?", "next_video": "Next: tea."},
                        "thumbnail_ideas": ["Rent wins", "Where it goes", "The catch"], "risks": []},
            "hooks": hooks}


def script(pack: str, outline: dict, hook_type: str) -> dict:
    prof = sp.get(pack)
    kids = pack == "kids"
    wps = prof["wps"]
    shots = ["wide", "close", "detail"]
    plants = {1: "L1", 2: "L2", 6: "L3", 9: "L4"}
    pays = {6: "L1", 8: "L2", 11: "L3", 15: "L4"}
    if kids:
        plants, pays = {1: "L1"}, {8: "L1"}
    segs = []
    for b in outline["beats"]:
        n = b["n"]
        words = max(6, int(b["seconds"] * wps))
        text = narration(words, n, kids, prof["sentence_max_words"])
        if n == 3 and not kids:
            text = "The firm reported 1.2 billion dollars. " + narration(words - 6, n, kids)
        fact_ids = ["f1"] if n == 3 and not kids else b["fact_ids"] if not kids else []
        if n == 1 and not kids:
            text = "Why does a cup cost four times more? " + narration(words - 8, n, kids)
        if n == 1 and kids:
            text = "Look at Pip! Where is the red ball? " + narration(words - 8, n, kids)
        seg = {"chapter": b["chapter"], "narration": text, "visual_keywords": ["cafe counter", "city street"],
               "visual_intent": {"shot_type": shots[(n - 1) % 3], "must_show": "a busy counter", "avoid": "logos"},
               "est_seconds": round(len(text.split()) / wps, 1),
               "emotion": b["emotion"], "beat": None if b["device"] == "explain" else b["device"],
               "fact_ids": fact_ids}
        if n in plants:
            seg["plants_loop"] = plants[n]
        if n in pays:
            seg["pays_loop"] = pays[n]
        segs.append(seg)
    last = segs[-1]
    last["narration"] += " What would you cut? Next video: tea."
    last["est_seconds"] = round(len(last["narration"].split()) / wps, 1)
    return {"topic": "how a shop makes money", "originality_note": "Own angle: rent is the real product.",
            "hook_type": hook_type, "arc": outline["arc"], "sensitive_topic": False, "synthetic_media": False,
            "titles": [{"text": f"How a shop really makes money {i}", "style": "how-x", "is_pick": i == 0}
                       for i in range(15)],
            "thumbnail_texts": ["Rent wins", "The catch", "Follow it"], "description_summary":
                "A clear look at where the money goes in a small shop, with the real numbers behind it." * 1,
            "tags": ["shop", "money", "rent", "economics", "business"],
            "sources": [{"id": "s1", "title": "Report", "url_or_note": "https://example.org/report1"}],
            "segments": segs, "cta": "What would you cut? Next video: tea."}


def review(draft: dict, pack: str = "explainer", hook_scores: int = 5) -> dict:
    """A review whose rewrite changes the quoted line in three segments and keeps everything else."""
    from studio.stages.story import criteria_for
    revised = copy.deepcopy(draft)
    swipes = []
    plan_ = []
    for idx in (3, 5, 7):
        seg = revised["segments"][idx]
        first = seg["narration"].split(". ")[0] + "."
        swipes.append({"segment": idx + 1, "quote": first, "why": "attention dips", "fix": "tighter line"})
        words = len(first.split())
        replacement = " ".join(["Fresh", "words", "land", "here"] * 10)[: 0] or " ".join(
            (["Now", "this", "is", "new", "and", "tight"] * 4)[:words])
        plan_.append((first, replacement.rstrip(".") + "."))
    for first, new in sorted(plan_, key=lambda x: -len(x[0])):  # longest first: a short quote may sit inside a long one
        for other in revised["segments"]:  # the quoted line must be gone wherever it appears
            other["narration"] = other["narration"].replace(first, new)
    return {"scores": {c: hook_scores for c in criteria_for(pack)}, "verdict": "Drags at the middle; tightened.",
            "swipe_points": swipes, "fixes": ["tighten the middle"], "revised": revised}


def write(project: Path, task: str, data: dict) -> Path:
    d = project / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{task}.response.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return f
