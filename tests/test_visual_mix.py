"""Charts and stills are rare; cast scenes are the default."""

from studio.history import cast
from studio.quality import visual_mix as vm
from studio.stages.visuals import chart_gaps


def _segs(n, chart_at, kind="bar"):
    return [{"chart_data": {"type": kind, "labels": ["a", "b"], "values": [1, 2]} if i in chart_at else None}
            for i in range(1, n + 1)]


def test_chart_cap_and_spacing():
    segs = _segs(30, {1, 2, 5, 9, 13, 17, 21})
    vm.limit_charts(segs)
    kept = [i for i, s in enumerate(segs, 1) if s["chart_data"]]
    assert len(kept) <= vm.MAX_CHARTS
    assert all(b - a > vm.MIN_CHART_GAP for a, b in zip(kept, kept[1:]))
    assert kept[0] == 1


def test_pie_becomes_animated_bar():
    segs = _segs(5, {2}, "pie")
    vm.limit_charts(segs)
    assert segs[1]["chart_data"]["type"] == "bar"


def test_default_cast_scene_and_no_chart_gap_warning():
    assert vm.cast_scene_for({}, cast.SCENE_TYPES) == vm.DEFAULT_CAST_SCENE
    assert vm.cast_scene_for({"scene": "skit"}, cast.SCENE_TYPES) == "skit"
    assert vm.cast_scene_for({"chart_data": {"type": "bar"}}, cast.SCENE_TYPES) is None
    assert chart_gaps(_segs(20, set())) == []
