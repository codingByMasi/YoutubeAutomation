"""Map scenes show the place the script names (approximate outlines, real names), not one invented landmass."""
from studio.history import maps, scene_plan
from studio.history import render as r
from tests.test_history_scenes_look import _scene


def _map(label_list, title="t", **extra):
    return {"scene": "map", "narration": "x", "cast": ["quill"],
            "scene_data": {"title": title, "points": [{"label": n, "x": 0.1, "y": 0.1} for n in label_list], **extra}}


def test_region_follows_the_places_named():
    pick = lambda labels, **k: maps.pick_region({"points": [{"label": n} for n in labels], **k})  # noqa: E731
    assert pick(["Plassey", "Calcutta"]) == "south_asia"
    assert pick(["Hong Kong", "Canton"]) == "east_asia"
    assert pick(["Britain", "India", "Africa", "Australia"]) == "world"
    assert pick(["Spain", "Alps"]) is None  # the Punic-war Mediterranean map is unchanged
    assert pick([], region="east_asia") == "east_asia"
    assert maps.pick_region({"title": "Opium War"}, "") == "east_asia"
    assert maps.pick_region({"title": "?"}, "nothing known") == "world"


def test_points_use_real_positions_and_unknown_places_are_dropped():
    pts = maps.resolve_points("south_asia", [{"label": "Calcutta"}, {"label": "Atlantis"}])
    assert [p["label"] for p in pts] == ["Calcutta"]
    cal = pts[0]
    assert 0.6 < cal["x"] < 0.7 and 0.25 < cal["y"] < 0.4  # eastern India, not a corner of the frame
    hk = maps.resolve_points("east_asia", [{"label": "Hong Kong"}])[0]
    assert 0.5 < hk["x"] < 0.6 and 0.7 < hk["y"] < 0.85


def test_each_region_draws_and_differs(tmp_path):
    frames = {}
    cases = {"india": ["Plassey", "Calcutta"], "china": ["Canton", "Hong Kong"], "world": ["Britain", "India"]}
    for name, labels in cases.items():
        frames[name] = _scene(tmp_path, _map(labels), 8.0).frame(7.0).tobytes()
    assert len(set(frames.values())) == 3
    assert r._geo_base("south_asia").size == (r.W, r.H)


def test_unknown_labels_do_not_crash_and_planner_keeps_known_regional_labels():
    assert maps.resolve_points("world", [{"label": "Nowhere"}]) == []
    segs = [{"narration": "The Company took Bengal."}]
    scene_plan.merge(segs, {"segments": [{"scene": "map", "cast": ["quill"],
                                          "scene_data": {"points": [{"label": "Plassey"}, {"label": "Calcutta"}]}}]})
    assert [p["label"] for p in segs[0]["scene_data"]["points"]] == ["Plassey", "Calcutta"]
