"""Quality gate and retention feedback loop (YouTube APIs mocked)."""

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from studio.errors import StudioError
from studio.growth import channels
from studio.models import Idea, Video
from studio.quality import feedback, gate, profiles, rules
from studio.stages import review
from studio.stages.timing import HOOK_SHOT_MAX, SHOT_MAX, shot_max_for
from tests.conftest import Answers
from tests.test_review_publish import ready_video

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def pkg():
    return copy.deepcopy(SAMPLE)


def flat_curve(hook_loss=0.45, dip=0.0):
    """Mock-API style curve: (elapsed ratio, watch ratio)."""
    pts = [(i / 20, max(0.05, 1 - hook_loss * min(1, (i / 20) / 0.05) - 0.3 * max(0, i / 20 - 0.05)))
           for i in range(21)]
    return [(x, y - (dip if 0.45 <= x <= 0.55 else 0)) for x, y in pts]


# ---------- gate ----------
def test_sample_scores_and_has_all_dimensions():
    r = gate.evaluate(pkg(), "explainer", audio={"lufs": -16.0, "true_peak": -2.0})
    assert set(r["dimensions"]) == set(profiles.DIMENSIONS)
    assert r["verdict"] in ("pass", "warn") and r["score"] >= 55


def test_weak_hook_and_missing_cta_are_flagged():
    d = pkg()
    d["segments"][0]["narration"] = "Hey guys, welcome back to the channel, today we look at coffee."
    d["segments"][-1]["narration"] = "That is all for today."
    r = gate.evaluate(d, "explainer")
    texts = " ".join(i["text"] for i in r["issues"])
    assert "greeting" in texts and "call to action" in texts
    assert r["dimensions"]["hook"] < 60


def test_banned_phrase_and_missing_sources_block():
    d = pkg()
    d["segments"][1]["narration"] = "This is guaranteed to make you rich."
    d["sources"] = []
    r = gate.evaluate(d, "explainer")
    assert r["verdict"] == "block"
    assert any("Banned phrase" in x for x in gate.blocking_reasons(r))


def test_audio_loudness_and_peak():
    ok = gate.evaluate(pkg(), "explainer", audio={"lufs": -16.2, "true_peak": -2.0})
    bad = gate.evaluate(pkg(), "explainer", audio={"lufs": -9.0, "true_peak": 0.5})
    assert ok["dimensions"]["audio"] == 100
    assert bad["dimensions"]["audio"] < 60
    assert gate.evaluate(pkg(), "explainer")["dimensions"]["audio"] < 100  # not measured: noted, not silent


def test_visual_variety_cards_only_is_penalised():
    d = pkg()
    for s in d["segments"]:
        s["visual"] = {"kind": "card", "paths": []}
    r = gate.evaluate(d, "explainer")
    assert any("plain cards" in i["text"] for i in r["issues"]) and r["dimensions"]["visuals"] < 80


def test_pacing_beat_gap_respects_channel_type_and_tuning():
    d = pkg()
    for s in d["segments"]:
        s.pop("beat", None)
        s.pop("chart_data", None)
        s["est_seconds"] = 30
    explainer = gate.evaluate(d, "explainer")
    kids = gate.evaluate(d, "kids")
    tight = gate.evaluate(d, "explainer", tuning={"beat_gap_max": 20})
    assert sum("retention beat" in i["text"] for i in kids["issues"]) >= \
        sum("retention beat" in i["text"] for i in explainer["issues"])
    assert tight["tuning"]["beat_gap_max"] == 20 and tight["dimensions"]["pacing"] <= explainer["dimensions"]["pacing"]


def test_thresholds_only_accept_tunable_keys():
    t = profiles.thresholds("explainer", {"hook_max_seconds": 9, "block_below": 0, "weights": 1})
    assert t["hook_max_seconds"] == 9 and t["block_below"] == 55 and isinstance(t["weights"], dict)


def test_channel_type_from_profile_or_niche():
    assert profiles.channel_type({"channel_type": "story"}) == "story"
    assert profiles.channel_type({"niche": "Nursery rhymes for toddlers"}) == "kids"
    assert profiles.channel_type({"niche": "Economics"}) == "explainer"


def test_gate_run_writes_report(ctx, capsys):
    v = ready_video(ctx)
    r = gate.run(ctx, v.id, echo=print)
    assert (ctx.settings.project_dir(v.id) / "gate.json").exists() and r["video_id"] == v.id
    assert "Quality gate" in capsys.readouterr().out


def test_review_blocks_weak_video_unless_accepted(ctx):
    v = ready_video(ctx)
    p = json.loads((ctx.settings.project_dir(v.id) / "script.json").read_text())
    p["segments"][1]["narration"] = "This is guaranteed to work."
    (ctx.settings.project_dir(v.id) / "script.json").write_text(json.dumps(p))
    ctx.confirm = Answers("yes")
    with pytest.raises(StudioError):
        review.run(ctx, v.id)
    assert v.stage == "thumbnailed" and ctx.confirm.asked == []


def test_review_yes_still_required_when_gate_passes(ctx):
    v = ready_video(ctx)
    ctx.confirm = Answers("no")
    with pytest.raises(Exception):  # noqa: B017  GateError from the typed-yes gate
        review.run(ctx, v.id)
    assert ctx.confirm.asked and v.stage == "thumbnailed"


# ---------- feedback ----------
def rec(video_id=1, hook_loss=0.45, **kw):
    return {"video_id": video_id, "duration": 600, "curve": flat_curve(hook_loss), "ctr": 0.05, "source": "youtube", **kw}


def test_curve_at_interpolates():
    c = [(0, 1.0), (0.5, 0.5), (1.0, 0.0)]
    assert feedback.curve_at(c, 0.25) == pytest.approx(0.75) and feedback.curve_at(c, 2) == 0.0


def test_features_find_hook_loss_and_drop():
    f = feedback.features(rec(), pkg())
    assert 0.4 < f["hook_retention"] < 0.65 and f["worst_drop"] > 0
    deep = feedback.features({**rec(), "curve": flat_curve(0.45, dip=0.25)}, pkg())
    assert deep["worst_drop"] > f["worst_drop"]


def test_derive_tightens_for_weak_hook_and_keeps_when_good():
    weak = feedback.derive([feedback.features(rec(hook_loss=0.6))], "explainer", "youtube")
    assert weak["tuning"]["hook_max_seconds"] < 15 and weak["edit"]["hook_shot_max_seconds"] < HOOK_SHOT_MAX
    good_curve = [(x / 20, 1 - 0.3 * x / 20) for x in range(21)]
    good = feedback.derive([feedback.features({**rec(), "curve": good_curve})], "explainer", "youtube")
    assert not good["tuning"] and good["lessons"][0]["area"] == "keep"


def test_kids_target_is_stricter_than_explainer():
    f = feedback.features(rec(hook_loss=0.38))
    assert "hook_max_seconds" not in feedback.derive([f], "explainer", "youtube")["tuning"]
    assert "hook_max_seconds" in feedback.derive([f], "kids", "youtube")["tuning"]


class FakeAnalytics:
    def __init__(self, curve):
        self.curve = curve

    def retention(self, yt, start, end):
        return self.curve

    def daily(self, yt, start, end):
        return [{"views": 10}]

    def thumbnail_daily(self, yt, start, end):
        return [{"ctr": 0.02}]


def published(ctx, n=1):
    for _ in range(n):
        idea = Idea(seed="s", topic="t", status="approved", channel_id=ctx.session.info.get("channel_id", "default"))
        ctx.session.add(idea)
        ctx.session.flush()
        v = Video(idea_id=idea.id, stage="live", youtube_video_id=f"yt{idea.id}")
        ctx.session.add(v)
        ctx.session.commit()
        out = ctx.settings.project_dir(v.id)
        (out / "script.json").write_text(json.dumps(dict(pkg(), build={"duration": 600})))


def test_live_learning_applies_to_gate_script_prompt_and_edit(ctx):
    published(ctx, 2)
    data = feedback.run(ctx, mode="live", analytics=FakeAnalytics(flat_curve(0.6)), echo=lambda *_: None)
    assert data["source"] == "youtube" and data["videos"] == 2
    root = ctx.settings.root
    assert rules.tuning(rules.load(root))["hook_max_seconds"] < 15
    assert "retention data" in rules.lessons_text(root)
    from studio.stages import script as sc
    assert "retention data" in sc.build_prompt(root, "coffee")
    assert shot_max_for(1, rules.edit_limits(root)) < HOOK_SHOT_MAX
    assert shot_max_for(2, rules.edit_limits(root)) <= SHOT_MAX
    assert shot_max_for(2) == SHOT_MAX  # no limits: unchanged behaviour
    assert gate.evaluate(pkg(), "explainer", rules.tuning(rules.load(root)))["tuning"]["hook_max_seconds"] < 15


def test_auto_falls_back_to_mock_and_mock_is_advisory(ctx):
    msgs = []
    data = feedback.run(ctx, mode="auto", echo=msgs.append)  # no credentials: analytics unavailable
    assert data["source"] == "mock" and any("MOCK" in m for m in msgs)
    root = ctx.settings.root
    assert rules.tuning(rules.load(root)) == {} and rules.lessons_text(root) == "" and rules.edit_limits(root) == {}
    feedback.run(ctx, mode="mock", apply_mock=True, echo=lambda *_: None)
    assert rules.lessons_text(root) != ""


def test_live_mode_without_data_is_a_clear_error(ctx):
    with pytest.raises(StudioError) as e:
        feedback.run(ctx, mode="live", analytics=FakeAnalytics([]), echo=lambda *_: None)
    assert "No retention data" in str(e.value) and "Next:" in str(e.value)


def test_rules_are_separate_per_channel(ctx):
    root = ctx.settings.root
    channels.add(root, "Money Maps", channel_type="explainer")
    feedback.run(ctx, mode="mock", apply_mock=True, echo=lambda *_: None)
    assert rules.load(root)["lessons"]
    channels.add(root, "Kids Corner", channel_type="kids")
    assert rules.load(root)["lessons"] == []  # a new channel starts clean
    feedback.run(ctx, mode="mock", apply_mock=True, echo=lambda *_: None)
    assert rules.load(root)["channel_type"] == "kids"
    channels.switch(root, "money-maps")
    assert rules.load(root)["channel_type"] == "explainer"


def test_mock_curve_is_deterministic():
    assert feedback.mock_curve(3) == feedback.mock_curve(3) != feedback.mock_curve(4)
    assert date.today()  # keep import used
