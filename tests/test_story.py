"""Outline, critique/rewrite and QA: the story side of quality."""

import copy
import json
from pathlib import Path

import pytest

from studio.errors import PendingLLMResponse, StageError, StudioError
from studio.models import Idea, Video
from studio.stages import qa, story
from studio.stages import script as sc

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def good_outline() -> dict:
    beats = [{"n": i, "chapter": f"Part {i}", "purpose": "p", "seconds": 12 if i == 1 else 20,
              "device": "explain" if i % 3 == 0 else "reveal", "key_fact": "$5 (s1)", "emotion": "curiosity"}
             for i in range(1, 13)]
    return {
        "audience_question": "Where does my $5 go?", "big_idea": "The cup is the cheap part.",
        "promise": "You will see the money flow.", "title_promise": "Where your $5 goes",
        "hooks": [{"formula": "number_stakes", "line": "A $5 coffee costs 30 cents to make. Where does the rest go?",
                   "why": "gap", "pick": True},
                  {"formula": "contradiction", "line": "The coffee is not the product.", "why": "x"},
                  {"formula": "hidden_answer", "line": "Why does coffee lose money and win?", "why": "x"}],
        "loops": [{"plant": 1, "question": "q1", "payoff": 6}, {"plant": 2, "question": "q2", "payoff": 9},
                  {"plant": 4, "question": "q3", "payoff": 11}],
        "beats": beats, "arc": {"setup": "a", "escalation": "b", "twist": "c", "payoff": "d"},
        "ending": {"callback": "c", "takeaway": "t", "cta_question": "q", "next_video": "n"},
        "thumbnail_ideas": ["a", "b", "c"], "sources": [{"id": "s1", "title": "t", "url_or_note": "u"}], "risks": []}


def test_good_outline_passes():
    assert story.validate_outline(good_outline()) == []


def test_outline_rules():
    d = good_outline()
    d["hooks"][0]["line"] = ("Hey everyone and welcome to a brand new video about how "
                             "coffee shops really make their money.")
    d["beats"][0]["seconds"] = 30
    d["loops"] = d["loops"][:2]
    for b in d["beats"][3:7]:
        b["device"] = "explain"
    d["ending"]["cta_question"] = ""
    problems = "\n".join(story.validate_outline(d))
    for expected in ("first sentence", "hook: at most 15", "at least 3 open loops", "explain beats in a row",
                     "ending.cta_question"):
        assert expected in problems


def test_loop_payoff_must_follow_plant_and_start_early():
    d = good_outline()
    d["loops"] = [{"plant": 8, "question": "q", "payoff": 3}, {"plant": 9, "question": "q", "payoff": 10},
                  {"plant": 10, "question": "q", "payoff": 11}]
    problems = "\n".join(story.validate_outline(d))
    assert "first 60 seconds" in problems and "payoff must come after plant" in problems


def make_video(ctx):
    idea = Idea(seed="coffee", topic=SAMPLE["topic"], status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage="approved")
    ctx.session.add(v)
    ctx.session.commit()
    (ctx.settings.project_dir(v.id) / "prompts").mkdir(exist_ok=True)
    return idea, v


def test_outline_flow_and_script_prompt_includes_it(ctx):
    idea, v = make_video(ctx)
    with pytest.raises(PendingLLMResponse):
        story.run_outline(ctx, idea.id)
    prompt = (ctx.settings.project_dir(v.id) / "prompts" / "outline.prompt.md").read_text()
    assert "Hook formula library" in prompt and "number_stakes" in prompt
    (ctx.settings.project_dir(v.id) / "prompts" / "outline.response.json").write_text(json.dumps(good_outline()))
    story.run_outline(ctx, idea.id)
    outline = story.load_outline(ctx.settings.project_dir(v.id))
    script_prompt = sc.build_prompt(ctx.settings.root, "coffee", outline)
    assert "Where does my $5 go?" in script_prompt and "Hook formula library" in script_prompt
    assert "No outline was made" in sc.build_prompt(ctx.settings.root, "coffee")


def test_bad_outline_is_rejected(ctx):
    idea, v = make_video(ctx)
    (ctx.settings.project_dir(v.id) / "prompts" / "outline.response.json").write_text(json.dumps({"beats": []}))
    with pytest.raises(StudioError) as e:
        story.run_outline(ctx, idea.id)
    assert "failed validation" in str(e.value)


def critique_answer(pkg: dict, **scores) -> dict:
    s = {c: 4 for c in story.CRITERIA} | scores
    return {"scores": s, "verdict": "The hook is slow. The rewrite starts on the number.",
            "fixes": ["'Welcome' -> greeting -> start on $5"], "revised": pkg}


def scripted(ctx):
    idea, v = make_video(ctx)
    (ctx.settings.project_dir(v.id) / "prompts" / "script.response.json").write_text(json.dumps(SAMPLE))
    sc.run(ctx, idea.id)
    return idea, v


def test_critique_applies_rewrite_and_keeps_original(ctx):
    idea, v = scripted(ctx)
    with pytest.raises(PendingLLMResponse):
        story.run_critique(ctx, v.id)
    out = ctx.settings.project_dir(v.id)
    prompt = (out / "prompts" / "critique.prompt.md").read_text()
    assert "payoff_ending" in prompt and "Current script package" in prompt
    revised = copy.deepcopy(SAMPLE)
    revised["segments"][0]["narration"] = "A five dollar coffee costs thirty cents to make. Where does the rest go?"
    (out / "prompts" / "critique.response.json").write_text(json.dumps(critique_answer(revised, hook=2)))
    story.run_critique(ctx, v.id)
    assert "thirty cents" in sc.load_package(ctx, v.id)["segments"][0]["narration"]
    assert json.loads((out / "script.original.json").read_text())["segments"][0]["narration"] != \
        revised["segments"][0]["narration"]
    assert (out / "critique.json").exists()
    story.run_critique(ctx, v.id)  # second run does not re-apply or overwrite the original
    assert json.loads((out / "script.original.json").read_text())["segments"][0]["narration"] == \
        SAMPLE["segments"][0]["narration"]


def test_critique_rejects_invalid_scores_and_invalid_rewrite(ctx):
    idea, v = scripted(ctx)
    bad = copy.deepcopy(SAMPLE)
    bad["segments"][0]["est_seconds"] = 40  # hook too long: the rewrite must obey the script rules
    ans = critique_answer(bad)
    ans["scores"]["hook"] = 9
    problems = "\n".join(story.validate_critique(ans))
    assert "scores.hook" in problems and "revised script" in problems and "hook" in problems


def test_critique_refused_after_voice(ctx):
    idea, v = scripted(ctx)
    v.stage = "voiced"
    ctx.session.commit()
    with pytest.raises(StageError) as e:
        story.run_critique(ctx, v.id)
    assert "voiced" in str(e.value)


# ---------- QA ----------
def seg(text, **kw):
    return {"narration": text, "est_seconds": 12, "visual_keywords": ["x"], "chapter": "c", **kw}


def test_qa_flags_weak_hook_ending_and_pacing():
    pkg = {"segments": [seg("Welcome back to the channel, today we talk about coffee.")]
           + [seg("The business sells coffee in cups every single day to many people.", est_seconds=40)
              for _ in range(6)]}
    text = "\n".join(qa.quality_report(pkg)["warnings"])
    assert "greeting" in text and "open loop" in text and "call to action" in text
    assert "retention beat" in text


def test_qa_accepts_strong_script():
    segs = [seg("A $5 coffee costs 30 cents. Where does the rest go?", beat="question"),
            seg("But first, hold that number. The third source is the one nobody notices.", beat="reveal"),
            seg("Here is the catch. Rent takes $1.20.", beat="reveal"),
            seg("Now compare two shops.", beat="example"),
            seg("That is not even where the real profit hides.", beat="pattern_break"),
            seg("So the cup is cheap. Comment which cost surprised you, and subscribe for the next video.",
                beat="reveal")]
    rep = qa.quality_report({"segments": segs})
    assert not [w for w in rep["warnings"] if "greeting" in w or "open loop" in w or "call to action" in w]


def test_qa_flags_cards_and_repeats():
    s = seg("Money moves. Where?", visual={"kind": "card", "paths": ["a.png"]})
    t = seg("x" * 5, est_seconds=40, visual={"kind": "clip", "paths": ["a.mp4"]})
    flags = qa.segment_flags(2, t)
    assert any("repetitive" in f for f in flags)
    assert any("plain title card" in f for f in qa.segment_flags(1, s))
