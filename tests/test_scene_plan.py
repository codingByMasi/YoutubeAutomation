# ruff: noqa: E501
"""One-line 'No scenes assigned' message, then Claude assigns scenes once; rules fill in if Claude fails."""
import pytest

from studio import llm
from studio.errors import PendingLLMResponse
from studio.history import scene_plan
from tests.test_history_autoscene import SEGS


class _S:  # the bits of Settings that ask_json is replaced for in these tests
    llm_provider = "claude_code"


def _answer(n):
    rows = [{"n": i + 1, "scene": "skit", "cast": ["quill", "dusty"], "speech": [{"who": "quill", "text": "Short line."}],
             "scene_data": {}} for i in range(n)]
    rows[2] = {"n": 3, "scene": "lectern", "cast": ["quill"], "scene_data": {"title": "x"}}
    rows[4] = {"n": 5, "scene": "lectern", "cast": ["quill"], "scene_data": {"title": "x"}}
    rows[1] = {"n": 2, "scene": "map", "cast": ["vex"], "scene_data": {"points": [
        {"x": 9, "y": 9, "label": "Spain"}, {"x": 9, "y": 9, "label": "Rome"}, {"x": 9, "y": 9, "label": "Atlantis"}]}}
    return {"segments": rows}


def test_prompt_lists_every_segment_and_forbids_photos():
    p = scene_plan.build_prompt([dict(s) for s in SEGS])
    assert f"exactly {len(SEGS)} entries" in p and "Photos and charts are NOT scene types" in p


def test_validate_catches_bad_answers():
    assert scene_plan.validate({"segments": []}, 3)
    bad = {"segments": [{"scene": "photo"}] * 3}
    assert any("scene" in x for x in scene_plan.validate(bad, 3))
    assert scene_plan.validate(_answer(len(SEGS)), len(SEGS)) == []


def test_claude_answer_is_merged_and_map_points_use_studio_places(monkeypatch, tmp_path):
    segs = [dict(s) for s in SEGS]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: _answer(len(segs)))
    said = []
    assert scene_plan.assign(_S(), tmp_path, segs, said.append) == "claude"
    assert said == [scene_plan.ONE_LINE]
    assert segs[1]["scene"] == "map"
    labels = [p["label"] for p in segs[1]["scene_data"]["points"]]
    assert labels == ["Spain", "Rome"] and segs[1]["scene_data"]["points"][0]["x"] != 9


def test_pending_answer_propagates(monkeypatch, tmp_path):
    def pending(*a, **k):
        raise PendingLLMResponse("Prompt written.", "claude_code", "Answer the prompt.")
    monkeypatch.setattr(llm, "ask_json", pending)
    with pytest.raises(PendingLLMResponse):
        scene_plan.assign(_S(), tmp_path, [dict(s) for s in SEGS], lambda m: None)


def test_provider_failure_falls_back_to_rules(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(llm, "ask_json", boom)
    segs = [dict(s) for s in SEGS]
    said = []
    assert scene_plan.assign(_S(), tmp_path, segs, said.append) == "rules"
    assert not scene_plan.missing(segs) and "built-in rules" in said[-1]


def test_nothing_to_do_when_scenes_exist(tmp_path):
    segs = [{"narration": "x y z", "scene": "skit"}]
    said = []
    scene_plan.assign(_S(), tmp_path, segs, said.append)
    assert said == []


def test_health_offers_the_one_button():
    from studio import health
    cause, fix = health.diagnose("visuals", "No scenes assigned for this script.")
    assert fix == "assign_scenes" and health.fix_label(fix) == "Assign scenes with Claude"
