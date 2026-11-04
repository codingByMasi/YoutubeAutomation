"""Diagram scenes show the script's real steps, never 'Step one / Step two / Step three'."""
from studio.history import autoscene
from studio.history import render as r
from tests.test_history_scenes_look import _scene

NARR = ("A company raises money from shareholders. Then it hires ships and soldiers. "
        "Finally conquered land pays the bills and the dividends.")


def test_steps_come_from_narration_when_missing_or_placeholder():
    for given in (None, [], ["Step one", "Step two", "Step three"]):
        steps = autoscene.steps_for(NARR, given)
        assert len(steps) == 3 and not any(s.lower().startswith("step ") for s in steps)
        assert steps[0].startswith("A company raises money")


def test_real_steps_are_kept():
    assert autoscene.steps_for(NARR, ["Borrow", "Invade", "Collect"]) == ["Borrow", "Invade", "Collect"]


def test_short_narration_splits_on_then():
    steps = autoscene.steps_for("The Company lends money to a king, then takes a port as payment", None)
    assert len(steps) == 2


def test_diagram_scene_renders_without_placeholder_text(tmp_path, monkeypatch):
    seen = []
    orig = r.centered
    monkeypatch.setattr(r, "centered", lambda d, xy, text, *a, **k: (seen.append(text), orig(d, xy, text, *a, **k))[1])
    sc = _scene(tmp_path, {"scene": "diagram", "narration": NARR, "cast": ["quill"], "scene_data": {"title": "t"}}, 8.0)
    sc.frame(7.0)
    assert not any("Step one" in str(x) for x in seen)
    assert any("shareholders" in str(x).lower() or "raises" in str(x).lower() for x in seen), seen
