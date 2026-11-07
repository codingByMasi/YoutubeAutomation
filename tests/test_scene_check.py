"""Automatic checks of drawn scenes: text fit, overlapping text, backdrop vs place, mouths."""
from studio.history import render as r
from studio.history import scene_check as sc
from studio.story import profile as sprofile


def test_text_outside_the_picture_or_on_top_of_other_text_is_reported():
    items = [("ATLANTIC OCEAN", (-30, 300, 200, 340)), ("Paris", (500, 100, 600, 150)),
             ("London", (560, 110, 660, 160)), ("Fine", (700, 400, 800, 440))]
    probs = sc.text_problems(items)
    assert any("ATLANTIC OCEAN" in p and "edge" in p for p in probs)
    assert any("'Paris'" in p and "'London'" in p and "overlap" in p for p in probs)
    assert not any("Fine" in p for p in probs)
    assert sc.text_problems([("A", (10, 10, 50, 50)), ("A", (10, 10, 50, 50))]) == []  # a shadow is not an overlap


def test_backdrop_must_fit_the_place_the_script_describes():
    base = {"scene": "skit", "staging": "Two officials in an office.", "visual_keywords": ["ledger"]}
    assert sc.backdrop_problems(base) == []
    assert sc.backdrop_problems({**base, "scene_data": {"backdrop": "sea"}})  # sea with no sea in the setting
    assert sc.backdrop_problems({**base, "scene_data": {"backdrop": "volcano"}})  # not a known backdrop
    at_sea = {**base, "staging": "On the deck of a ship at sea.", "scene_data": {"backdrop": "sea"}}
    assert sc.backdrop_problems(at_sea) == []
    assert sc.backdrop_problems({**base, "staging": "Soldiers in the snow.", "scene_data": {"backdrop": "hall"}})
    assert sc.backdrop_problems({"scene": "map"}) == []


def test_the_narration_needs_a_visible_speaker_and_nobody_else_may_mouth_it(tmp_path, monkeypatch):
    seg = {"scene": "title", "cast": [], "scene_data": {"title": "T"}, "narration": "x"}
    cast = r.Cast(tmp_path)
    assert sc.mouth_problems({**seg, "_narrator": "Storyteller"}, 6.0, cast) == []
    monkeypatch.setattr(r.Scene, "narrating", lambda self, t: False)  # nobody's mouth follows the voice
    assert any("no visible speaker" in p for p in sc.mouth_problems(seg, 6.0, cast))
    monkeypatch.undo()
    skit = {"scene": "skit", "cast": ["A", "B"], "narration": "x", "_narrator": "Storyteller", "narr_seconds": 6.0,
            "lines_at": 6.4, "speech": [{"who": "A", "text": "Hi."}]}
    assert sc.mouth_problems(skit, 10.0, cast) == []
    real = r.Scene.actor

    def chatty(self, img, who, cx, bottom, px, t, i, talking, *a, **k):  # a cast figure talks to the narration
        return real(self, img, who, cx, bottom, px, t, i, self.mouth(t) if who in ("A", "B") else talking, *a, **k)
    monkeypatch.setattr(r.Scene, "actor", chatty)
    assert any("figure in the scene" in p for p in sc.mouth_problems(skit, 10.0, cast))


def test_a_line_spoken_by_someone_who_is_not_on_screen_is_reported():
    seg = {"scene": "skit", "cast": ["Napoleon", "Pope Pius VII"],
           "speech": [{"who": "Pope", "text": "x"}, {"who": "Joseph", "text": "y"}]}
    probs = sc.speaker_problems(seg)
    assert len(probs) == 1 and "Joseph" in probs[0]  # "Pope" matches "Pope Pius VII"
    assert sc.speaker_problems({"scene": "map"}) == []


def test_check_package_is_clean_for_good_scenes_and_names_the_bad_one():
    good = {"narrator": "Storyteller", "segments": [
        {"scene": "title", "chapter": "A", "scene_data": {"title": "Who started the fires? Disputed."}, "cast": [],
         "real_seconds": 6.0},
        {"scene": "map", "chapter": "B", "cast": [], "real_seconds": 6.0,
         "scene_data": {"region": "world", "points": [{"label": "London"}, {"label": "Paris"}]}},
        {"scene": "skit", "chapter": "C", "cast": ["A", "B"], "real_seconds": 8.0, "staging": "A harbour at sea.",
         "scene_data": {"backdrop": "sea"}, "speech": [{"who": "A", "text": "Hi."}]}]}
    assert sc.check_package(good) == []
    office = good["segments"][2] | {"staging": "An office.", "chapter": "Office"}
    bad = {"narrator": "Storyteller", "segments": [office]}
    probs = sc.check_package(bad)
    assert len(probs) == 1 and probs[0].startswith("Segment 1 (skit, Office)") and "'sea'" in probs[0]
    plain = {"segments": [{"narration": "plain", "est_seconds": 5}]}
    assert sc.check_package(plain) == []  # no scenes: nothing to check


def test_qa_runs_the_scene_check_for_story_channels_only():
    from studio.stages.qa import quality_report
    seg = {"narration": "A. B.", "est_seconds": 10, "real_seconds": 10, "scene": "skit", "cast": ["A"],
           "chapter": "Office", "staging": "An office.", "scene_data": {"backdrop": "sea"},
           "visual_keywords": ["x"]}
    pkg = {"segments": [seg] * 6}
    on = quality_report(pkg, sprofile.get("history"))
    off = quality_report(pkg, sprofile.get("business"))
    assert any(w.startswith("Scene check:") and "'sea'" in w for w in on["warnings"])
    assert not any(w.startswith("Scene check:") for w in off["warnings"])


def test_a_map_name_at_the_border_stays_whole():
    seg = {"scene": "map", "cast": [], "scene_data": {"region": "world", "points": [{"label": "Panama"}]}}
    for _ in range(1):
        with sc.record_text() as items:
            r.Scene(seg, 6.0, r.Cast("."), [0.0] * 200, 0).frame(5.0)
    assert sc.text_problems(items) == []


def test_a_diagram_step_with_text_cut_or_over_the_box_edge_is_reported():
    seg = {"scene": "diagram", "narration": "x", "scene_data": {"steps": ["Picture a bathtub", "Two taxes"]}}
    cw, x0 = r.diagram_layout(2)
    ok = [("Picture a", (x0 + 20, 300, x0 + cw - 20, 330)), ("bathtub", (x0 + 20, 340, x0 + cw - 20, 370)),
          ("Two taxes", (x0 + cw + 80, 300, x0 + 2 * cw + 20, 330))]
    assert sc.diagram_problems(seg, ok) == []
    cut = ok[:2]  # the second step never drawn
    assert any("step 2" in p and "cut short" in p for p in sc.diagram_problems(seg, cut))
    over = [ok[0], ("bathtub", (x0 + 20, 340, x0 + cw + 12, 370)), ok[2]]
    assert any("step 1" in p and "edge" in p for p in sc.diagram_problems(seg, over))


def test_a_picture_that_holds_still_is_reported(tmp_path, monkeypatch):
    seg = {"scene": "title", "cast": [], "scene_data": {"title": "Hello"}, "narration": "x"}
    moving = r.Scene(seg, 12.0, r.Cast(tmp_path), [0.0] * 400, 0)
    assert sc.still_problems(moving, 12.0) == []  # the camera beats keep it alive
    frozen = r.Scene(seg, 12.0, r.Cast(tmp_path), [0.0] * 400, 0)
    monkeypatch.setattr(frozen, "camera", lambda t: (1.0, 0.5, 0.5))
    monkeypatch.setattr(frozen, "frame", lambda t: r.backdrop("night").copy())
    probs = sc.still_problems(frozen, 12.0)
    assert probs and "holds still" in probs[0]
