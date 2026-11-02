"""Deterministic validators and helpers of the story engine (no network, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio import health
from studio.errors import StudioError
from studio.story import checks, facts, hooks, ledger, loops, mood, narration, safety, titles
from studio.story import models as M
from studio.story import profile as sp
from studio.story import visuals as sv
from tests import fake_llm

EXPL = sp.get("explainer")


def seg(text="Word.", sec=10, **kw):
    return {"narration": text, "est_seconds": sec, **kw}


# ---------- profiles ----------
def test_profiles_per_type_and_overrides():
    assert sp.pack_name("business") == "explainer" and sp.pack_name("history") == "history"
    assert sp.pack_name("kids") == "kids" and sp.pack_name("weird") == "general"
    h, k = sp.get("history"), sp.get("kids")
    assert (h["min_minutes"], h["max_minutes"], h["shot_interval"]) == (8, 15, (3, 6))
    assert (k["min_minutes"], k["max_minutes"], k["shot_interval"]) == (3, 8, (3, 5))
    assert EXPL["shot_interval"] == (4, 7) and EXPL["lufs_target"] == -14.0 and EXPL["true_peak"] == -1.0
    assert len(EXPL["banned_phrases"]) >= 40
    assert not sp.enabled(k, "fact_ledger") and sp.enabled(EXPL, "fact_ledger")
    off = sp.get("explainer", {"flags": {"loop_ids": False}, "min_minutes": 5})
    assert not sp.enabled(off, "loop_ids") and off["min_minutes"] == 5


def test_profile_for_channel_reads_story_override(root):
    from studio.growth import channels
    channels.update(root, channels.active_id(root), type="history", story={"flags": {"prosody": False}})
    p = sp.for_channel(root)
    assert p["name"] == "history" and not sp.enabled(p, "prosody")


# ---------- word count / sentences / banned ----------
def test_wordcount_range_and_est_seconds():
    pkg = {"segments": [seg(" ".join(["w"] * 25), 10), seg(" ".join(["w"] * 60), 10)]}
    probs = checks.wordcount_problems(pkg, EXPL)
    assert any("segment 2" in p for p in probs) and any("targets 8-12 min" in p for p in probs)


def test_sentence_cap_and_rhythm():
    long = " ".join(["word"] * 30) + "."
    assert checks.sentence_problems({"segments": [seg(long)]}, EXPL)
    even = " ".join(["Six words in every single sentence."] * 14)
    assert any("too even" in p for p in checks.sentence_problems({"segments": [seg(even)]}, EXPL))


def test_banned_list_whole_phrase_match():
    from studio.story.banned import banned_in
    assert banned_in("In today's video, we dive in.") and not banned_in("He studied the diet.", ["die"])


def test_reading_grade_cap_for_kids():
    hard = {"segments": [seg("Unquestionably, macroeconomic institutional frameworks necessitate comprehensive analysis.")]}  # noqa: E501
    assert checks.readability_problems(hard, sp.get("kids"))
    assert not checks.readability_problems({"segments": [seg("Pip has a red ball.")]}, sp.get("kids"))


# ---------- loops ----------
def loop_pkg(plants, pays, secs=60, n=8):
    segs = [seg(sec=secs) for _ in range(n)]
    for i, l in plants.items():  # noqa: E741
        segs[i]["plants_loop"] = l
    for i, l in pays.items():  # noqa: E741
        segs[i]["pays_loop"] = l
    return {"segments": segs}


def test_loop_validator():
    ok = loop_pkg({0: "L1", 0 + 1: "L2"}, {3: "L1", 4: "L2"})
    assert loops.loop_problems(ok, EXPL) == []
    assert any("no later payoff" in p for p in loops.loop_problems(loop_pkg({0: "L1", 1: "L2"}, {3: "L1"}), EXPL))
    assert any("never planted" in p for p in loops.loop_problems(loop_pkg({0: "L1", 1: "L2"}, {3: "L1", 4: "L9"}), EXPL))  # noqa: E501
    assert any("first 60s" in p for p in loops.loop_problems(loop_pkg({3: "L1", 4: "L2"}, {6: "L1", 7: "L2"}), EXPL))
    late = loop_pkg({0: "L1", 1: "L2"}, {8: "L1", 9: "L2"}, n=10)
    probs = loops.loop_problems(late, EXPL)
    assert any("last 20%" in p for p in probs) and any("payoff comes" in p for p in probs)


# ---------- facts ----------
def test_numeric_normalisation():
    assert facts.numbers_match(1.2e9, 1200e6) and facts.numbers_match(1.2, 1200) and not facts.numbers_match(1.2, 1.5)
    assert facts.figure_in_text("1.2 billion", "sales were 1,200 million in 2024")
    assert facts.figure_in_text(12, "growth of 12 percent")


def test_fact_verification_mocked_http(tmp_path):
    f = {"id": "f1", "claim": "c", "figure": 1.2, "unit": "B", "source_url": "https://x.org/a", "is_estimate": False,
         "quote_snippet": "the company reported 1.2 billion"}
    ok = facts.verify_fact(f, lambda u: (200, "In 2024 the company reported 1.2 billion in sales."), tmp_path)
    assert ok["status"] == "verified"
    quote = facts.verify_fact({**f, "figure": 7}, lambda u: (200, "The company reported 1.2 billion in sales."))
    assert quote["status"] == "verified"
    assert facts.verify_fact(f, lambda u: (200, "nothing relevant at all here"))["status"] == "unverified"
    assert facts.verify_fact(f, lambda u: (403, ""))["status"] == "unfetchable"
    assert facts.verify_fact(f, lambda u: (0, "ConnectionError"))["status"] == "unfetchable"
    assert facts.verify_fact({**f, "source_url": ""}, lambda u: (200, ""))["status"] == "unfetchable"
    calls = []
    cached = lambda u: (calls.append(u) or (200, "the company reported 1.2 billion"))  # noqa: E731
    facts.verify_fact(f, cached, tmp_path / "c")
    facts.verify_fact(f, cached, tmp_path / "c")
    assert len(calls) == 1  # second run is served from the cache


def test_numbers_must_trace_to_facts():
    fl = [{"id": "f1", "figure": 1.2e9, "status": "verified", "is_estimate": False},
          {"id": "f2", "figure": 5, "status": "unverified", "is_estimate": True}]
    good = {"segments": [seg("Sales were 1.2 billion dollars.", fact_ids=["f1"])]}
    assert facts.trace_problems(good, fl) == []
    bad = {"segments": [seg("Sales were 3.4 billion dollars.", fact_ids=["f1"])]}
    assert any("3.4 billion" in p for p in facts.trace_problems(bad, fl))
    unknown = {"segments": [seg("Hello there.", fact_ids=["f9"])]}
    assert any("unknown fact" in p for p in facts.trace_problems(unknown, fl))
    est = {"segments": [seg("Sales were 5 percent.", fact_ids=["f2"])]}
    assert any("word it as one" in p for p in facts.trace_problems(est, fl))
    assert facts.trace_problems({"segments": [seg("Sales were about 5 percent.", fact_ids=["f2"])]}, fl) == []
    chart = {"segments": [seg("Fine.", fact_ids=["f1"], chart_data={"values": [1.2e9, 7], "labels": ["a", "b"],
                                                                     "title": "Sales"})]}
    assert any("chart value 7" in p for p in facts.trace_problems(chart, fl))
    nf = [{"id": "f3", "figure": 2, "status": "unverified", "is_estimate": False}]
    assert any("not flagged is_estimate" in p
               for p in facts.trace_problems({"segments": [seg("Plain.", fact_ids=["f3"])]}, nf))


def test_validate_facts_shape():
    assert facts.validate_facts([])
    assert any("source_url" in p for p in facts.validate_facts([{"id": "f1", "claim": "c", "unit": "",
                                                                  "source_url": "", "is_estimate": False}]))


# ---------- hooks + ledger ----------
def variants(types):
    return [{"hook_type": t, "line": f"Why does {i} cost 4 times more? Find out by the end.", "why": "",
             "score": {"curiosity": 4, "clarity": 4, "stakes": 4, "promise": 4 if t != "cold_open" else 5}}
            for i, t in enumerate(types)]


def test_hook_rotation_avoids_last_three(root):
    types = EXPL["hook_formulas"][:4] * 2
    assert hooks.validate_variants(variants(types), EXPL) == []
    best, ranked = hooks.pick_best(variants(types), ["cold_open", "number_stakes", "contradiction"], EXPL)
    assert best["hook_type"] not in ("cold_open", "number_stakes", "contradiction") and not best["blocked"]
    for t in ("cold_open", "number_stakes", "contradiction"):
        ledger.record(root, {"video_id": ledger.load(root).__len__() + 1, "hook_type": t, "chapters": []})
    assert hooks.rotation_problem("cold_open", root, 3)
    assert hooks.rotation_problem("villain_system", root, 3) is None
    assert hooks.validate_variants(variants(["cold_open"] * 8), EXPL)  # too few distinct formulas


def test_repetition_ledger_structure_and_severity():
    def pkg(ch, opening):
        return {"hook_type": "x", "segments": [{"chapter": c, "narration": f"{opening} things. More.",
                                                "beat": "reveal", "visual_keywords": ["a"]} for c in ch]}
    chapters = ["the problem", "the myth", "the numbers", "the twist", "the takeaway"]
    a, b = ledger.entry_from_package(pkg(chapters, "Here is the")), ledger.entry_from_package(pkg(chapters, "Here is the"))  # noqa: E501
    issues = ledger.repetition_issues(a, [b])
    assert any("opening sentence" in i["text"] for i in issues) and any("structure" in i["text"] for i in issues)
    third = ledger.repetition_issues(a, [b, b])
    assert any(i["severity"] == "critical" for i in third)  # same structure the 3rd time
    fresh = ledger.entry_from_package(pkg(["intro", "case", "compare", "close"], "Picture this:"))
    assert not [i for i in ledger.repetition_issues(fresh, [b]) if i["severity"] == "critical"]
    assert "(no earlier videos" in ledger.prompt_text(Path("/nonexistent-root-for-test"))


# ---------- titles, models, safety ----------
def test_title_promise_and_ranking():
    pkg = {"titles": [{"text": "How Netflix really makes money", "is_pick": True}],
           "segments": [seg("Netflix makes money in a strange way."), seg("Here is how.")]}
    assert titles.promise_problems(pkg) == []
    pkg["segments"] = [seg("Welcome to the lecture on pottery."), seg("Clay is great.")]
    assert titles.promise_problems(pkg)
    ranked = titles.rank_titles([{"text": "WHY EVERYTHING IS SHOCKING"}, {"text": "Why 4 coffees cost a lunch?"}])
    assert ranked[0]["text"].startswith("Why 4")


def test_pydantic_models_give_field_paths():
    bad = fake_llm.plan("explainer")
    bad["outline"]["beats"][1]["seconds"] = "x"
    del bad["hooks"][0]["line"]
    probs = M.model_problems(M.StoryPlan, bad)
    assert any("outline.beats[1].seconds" in p for p in probs) and any("hooks[0].line" in p and "missing" in p for p in probs)  # noqa: E501
    assert M.model_problems(M.StoryPlan, fake_llm.plan("explainer")) == []


def test_safety_text_flags_kids_and_history():
    kids = {"segments": [seg("The big monster will hurt you.")]}
    assert safety.text_issues(kids, sp.get("kids"))[0]["severity"] == "critical"
    assert safety.text_issues({"segments": [seg("They were beheaded.")]}, sp.get("history"))
    assert safety.text_issues(kids, EXPL) == [] and safety.frame_issues([]) == []


# ---------- narration ----------
def test_prosody_pauses_and_groups():
    segs = [seg("a.", chapter="c1", emotion="hook"), seg("b.", chapter="c1", emotion="neutral", plants_loop="L1"),
            seg("c.", chapter="c1", emotion="reveal", beat="reveal"), seg("d.", chapter="c2")]
    assert narration.prosody_for(EXPL, "hook")["rate"] > 0 > narration.prosody_for(EXPL, "reveal")["rate"]
    assert narration.edge_args({"rate": 6, "pitch": -2, "volume": 0}) == {"rate": "+6%", "pitch": "-2Hz", "volume": "+0%"}  # noqa: E501
    assert narration.pause_after(EXPL, segs, 1) >= EXPL["voice"]["pauses"]["before_reveal"]
    assert narration.pause_after(sp.get("kids"), segs, 1) == 0.0  # kids: no pause before reveals
    assert narration.groups(segs, EXPL) == [[0], [1], [2], [3]]


def test_word_timing_split_and_sync_report():
    texts = ["one two three", "four five"]
    words = [(0.0, 0.3, "one"), (0.3, 0.6, "two"), (0.6, 0.9, "three"), (1.2, 1.5, "four"), (1.5, 1.9, "five")]
    cuts = narration.split_points(words, texts, 1.9)
    assert cuts == [1.05]
    per = narration.words_per_segment(words, texts, cuts)
    assert [w[2] for w in per[1]] == ["four", "five"] and per[1][0][0] == pytest.approx(0.15)
    assert narration.split_points(words[:2], texts, 1) is None  # counts do not line up: do not guess
    ref = [(s + 0.4, e + 0.4, w) for s, e, w in words]
    rep = narration.sync_report(words, ref, texts)
    assert rep and all(r["drift_ms"] == 400 for r in rep)
    assert narration.sync_report(words, [], texts) == []


def test_caption_sync_gate_dimension():
    from studio.story.gate_checks import story_issues
    issues = story_issues({"segments": [seg("x.")]}, EXPL, caption_sync=[{"segment": 1, "drift_ms": 400}])
    assert issues["captions"] and "400" in issues["captions"][0]["text"]
    assert not story_issues({"segments": [seg("x.")]}, EXPL, caption_sync=[{"segment": 1, "drift_ms": 100}])["captions"]


# ---------- music, visuals ----------
def test_mood_plan_drops_and_kids():
    segs = [seg(chapter="a", emotion="neutral"), seg(chapter="b", emotion="tense", beat="pattern_break"),
            seg(chapter="c", emotion="warm", beat="reveal")]
    spans = [(0, 10), (10, 20), (20, 30)]
    p = mood.plan(segs, spans, EXPL)
    assert [c[2] for c in p["chapters"]] == ["neutral", "tense", "resolve"] and p["drops"] == [10] and p["stingers"] == [20]  # noqa: E501
    assert mood.plan(segs, spans, sp.get("kids"))["drops"] == []


def test_visual_intent_queries_and_shot_rule(root):
    s = {"visual_keywords": ["busy street", "neon sign"], "visual_intent": {"must_show": "cashier at till", "avoid": "neon"}}  # noqa: E501
    assert sv.queries_for(s) == ["cashier at till", "busy street"]
    mk = lambda t: {"visual_intent": {"shot_type": t}}  # noqa: E731
    assert sv.shot_problems([mk("wide"), mk("wide"), mk("wide")]) and not sv.shot_problems([mk("wide"), mk("wide"), mk("close")])  # noqa: E501
    sv.record_assets(root, 1, ["u1", "u2"]); sv.record_assets(root, 2, ["u3"])  # noqa: E702
    assert sv.recent_assets(root, 3, exclude_video=2) == {"u1", "u2"}


def test_semantic_scorer_optional(monkeypatch):
    assert sv.best_candidate(None, "q", ["a", "b"]) == "a"  # no scorer: first candidate (tag overlap stays)
    class C:
        def __init__(self, u): self.page_url = u; self.path = None  # noqa: E702
    class Scorer(sv.SemanticScorer):
        def score(self, q, t, image=None): return 1.0 if "cashier" in t else 0.0  # noqa: E704
    assert sv.best_candidate(Scorer(), "cashier", [C("https://x/street"), C("https://x/cashier-till")]).page_url.endswith("till")
    import sys
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    assert sv.make_scorer() is None  # missing optional dependency: fallback, no crash


def test_ai_image_provider_defaults_to_null(monkeypatch, tmp_path):
    from studio.providers import ai_images, manim_scenes
    monkeypatch.delenv("AI_IMAGE_PROVIDER", raising=False)
    assert ai_images.make_ai_images().name == "none"
    monkeypatch.setenv("AI_IMAGE_PROVIDER", "diffusers")
    assert ai_images.make_ai_images().name == "none"  # no GPU/diffusers: degrades silently
    assert manim_scenes.render("timeline", {}, tmp_path / "x.mp4") is None


# ---------- health / fallbacks ----------
def test_issue_log_diagnosis_and_fix(root):
    it = health.record(root, "voice (edge)", ConnectionError("wss://speech.platform.bing.com failed"))
    assert "Edge voice" in it["cause"] and it["fix"] == "tts_fallback"
    assert health.record(root, "voice (edge)", ConnectionError("wss://speech.platform.bing.com failed"))["count"] == 2
    assert health.record(root, "x", "No module named 'rapidfuzz'")["fix"] == "pip:rapidfuzz"
    from studio.errors import PendingLLMResponse
    assert health.record(root, "script", PendingLLMResponse("wait")) is None
    msg = health.run_fix(root, it["id"])
    assert "Voice now tries" in msg and not [i for i in health.open_issues(root) if i["id"] == it["id"]]
    assert health.disable_flag(root, "prosody").startswith("Turned off")


def test_with_fallback_tries_next_and_reports(root):
    def boom():
        raise ConnectionError("network down")
    name, res = health.with_fallback(root, "voice", [("edge", boom), ("piper", lambda: "ok")])
    assert (name, res) == ("piper", "ok") and health.open_issues(root)
    with pytest.raises(StudioError) as e:
        health.with_fallback(root, "voice", [("edge", boom)])
    assert "Every option for voice failed" in str(e.value)


def test_tts_chain_skips_missing_engines(root):
    from studio.config import Settings
    from studio.providers.tts import FallbackTTS, get_tts
    settings = Settings(root=root, tts_provider="edge")
    t = get_tts(settings)  # kokoro/piper absent here -> plain edge engine
    assert t.name == "edge" or isinstance(t, FallbackTTS)
    class Bad:
        name = "bad"
        def synth(self, text, out, **k): raise ConnectionError("down")  # noqa: E704
    class Good:
        name = "good"
        def synth(self, text, out, **k): out.write_text("x"); return out  # noqa: E702
    fb = FallbackTTS([Bad(), Good()], root)
    out = root / "a.mp3"
    fb.synth("hi", out)
    assert out.exists() and fb.last_used == "good"


def test_loudness_target_is_configurable():
    from studio.util import ffmpeg
    assert "I=-14" in ffmpeg.loudnorm() and "I=-16:TP=-1.5" in ffmpeg.loudnorm(-16, -1.5)


def test_feedback_loop_needs_three_real_videos(root):
    from studio.growth import store
    from studio.story import feedback_loop as fl
    assert "not enough" in fl.prompt_text(root)
    row = lambda i, r: {"video_id": i, "hook_type": "cold_open", "hook_line": "x", "hook_retention": r,  # noqa: E731
                        "avg_view_pct": .4, "ctr": .05, "title_style": "how", "worst_drop": .2,
                        "drop": {"chapter": "c", "beat": "explain", "seconds": 90}}
    store.save(store.channel_file(root, fl.NAME), {str(i): row(i, .5 + i / 20) for i in range(1, 5)})
    txt = fl.prompt_text(root)
    assert "Worked best" in txt and "Worked worst" in txt
    assert any("explain" in l for l in fl.heatmap_lines(root))  # noqa: E741


# ---------- atomic critique replace ----------
def test_replace_package_is_atomic_and_numbered(ctx, monkeypatch):
    from studio.models import Segment
    from studio.stages import script as sc
    from tests.test_story_engine import make_video
    idea, v = make_video(ctx)
    pkg = fake_llm.script("explainer", fake_llm.plan("explainer")["outline"], "cold_open")
    sc.save_package(ctx, v, pkg)
    ctx.session.commit()
    new = json.loads(json.dumps(pkg))
    new["segments"][0]["narration"] = "A brand new opening line."
    assert sc.replace_package(ctx, v, new) == 1
    out = ctx.settings.project_dir(v.id)
    assert (out / "script.original.json").exists() and (out / "script.v1.json").exists()
    assert ctx.session.query(Segment).filter_by(video_id=v.id, position=1).one().narration == "A brand new opening line."  # noqa: E501
    third = json.loads(json.dumps(new))
    third["segments"][0]["narration"] = "Third version."

    def boom():
        raise RuntimeError("disk full")
    monkeypatch.setattr(ctx.session, "commit", boom)
    with pytest.raises(RuntimeError):
        sc.replace_package(ctx, v, third)
    monkeypatch.undo()
    assert json.loads((out / "script.json").read_text())["segments"][0]["narration"] == "A brand new opening line."
    assert ctx.session.query(Segment).filter_by(video_id=v.id, position=1).one().narration == "A brand new opening line."  # noqa: E501
