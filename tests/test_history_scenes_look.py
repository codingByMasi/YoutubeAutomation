# ruff: noqa: E501
"""Cast scenes: backdrops fit the words, crowds and close-up cuts, no burned captions on cast channels."""
from studio.history import render as r
from studio.story import profile as sprofile


def _scene(tmp_path, seg, dur=10.0):
    return r.Scene(seg, dur, r.Cast(tmp_path), [1.0] * int(dur * r.FPS), 0)


SKIT = {"scene": "skit", "narration": "The mercenary army gathered in the snow of the Alps.", "cast": ["Gaius", "Odo"],
        "staging": "A mercenary camp in the snow of the Alps.", "speech": [{"who": "Gaius", "text": "Where is our pay?"}, {"who": "Odo", "text": "Ask Rome."}]}


def test_backdrop_follows_the_words():
    assert r.guess_backdrop("crossing the Alps in winter") == "snow"
    assert r.guess_backdrop("the fleet sailed from the harbour") == "sea"
    assert r.guess_backdrop("they argued about the tax") == "market"
    assert r.guess_backdrop("nothing special") is None
    assert r.guess_backdrop("the pope frozen with shock; they bypass the guards") is None  # not snow
    for name in r.BACKDROPS:
        assert r.backdrop(name).size == (r.W, r.H)


def test_crowd_scene_draws_with_varied_extras(tmp_path):
    sc = _scene(tmp_path, {**SKIT, "scene_data": {**SKIT.get("scene_data", {}), "crowd": 14}})
    assert sc.crowd and sc.back == "snow"
    img = sc.frame(2.0)
    assert img.size == (r.W, r.H)
    looks = {sc.cast.extra(0, i, "#C0392B", 120, 0.0).tobytes() for i in range(4)}
    assert len(looks) == 4  # four different background people, not one copied figure


def test_no_background_crowd_unless_the_script_asks(tmp_path):
    assert not _scene(tmp_path, dict(SKIT)).crowd  # words like "army" or "people" no longer add extras


def test_camera_cuts_between_wide_and_close_up(tmp_path):
    sc = _scene(tmp_path, dict(SKIT))
    wide, close = sc.camera(1.0), sc.camera(5.0)
    assert wide[0] < 1.1 and close[0] > 1.25
    short = _scene(tmp_path, dict(SKIT), dur=4.0)
    assert short.camera(3.0)[0] < 1.1  # short scenes never cut
    lectern = _scene(tmp_path, {"scene": "lectern", "cast": ["Odo"], "scene_data": {"title": "t"}})  # older scripts
    assert lectern.camera(6.0)[0] < 1.1  # the chapter card must stay fully in frame


def test_cast_channels_do_not_burn_captions():
    assert sprofile.PACKS["history"]["flag_overrides"]["burn_captions"] is False
    assert sprofile.DEFAULT_FLAGS["burn_captions"] is True  # every other channel type keeps burned captions


def test_map_scene_draws_territories_and_a_marching_army(tmp_path):
    seg = {"scene": "map", "narration": "x", "cast": ["Hannibal"], "scene_data": {"title": "218 BC", "troops": 38000, "points": [
        {"x": 0.14, "y": 0.58, "label": "Spain"}, {"x": 0.58, "y": 0.30, "label": "Alps"}]}}
    sc = _scene(tmp_path, seg, 10.0)
    early, late = sc.frame(1.0), sc.frame(9.0)
    assert early.size == (r.W, r.H) and early.tobytes() != late.tobytes()
    assert r._territories(0).tobytes() != r._map_base().tobytes()  # the sides are tinted


def test_lectern_card_gets_a_line_from_the_narration_when_it_has_no_question():
    q = r.card_question("Back at the ledger. Page one says 125 shareholders. Who pays for the next volume?", "What Comes Next")
    assert q == "Who pays for the next volume?"
    assert r.card_question("It is 1600. A charter is signed.", "Rewind") == "A charter is signed."
    assert r.card_question("What Comes Next.", "What Comes Next") == ""  # never repeats the title
    assert r.card_question("A sentence far too long to fit on a chapter card " * 3, "T") == ""


def test_backdrop_comes_from_the_setting_not_from_the_narration_or_a_wrong_pick(tmp_path):
    base = {"scene": "skit", "cast": ["A"], "narration": "A ship sinks in a winter storm; he is frozen with shock.",
            "staging": "Two officials argue over a map in a candle-lit office.", "visual_keywords": ["map", "ledger"]}
    sc = r.Scene(base, 5.0, r.Cast(tmp_path), [1.0] * 130, 0)
    assert sc.back == "hall"  # the narration's ship, winter and frozen do not move a room to sea or snow
    snowy = {**base, "visual_intent": {"must_show": "soldiers marching through deep snow"}}
    assert r.Scene(snowy, 5.0, r.Cast(tmp_path), [1.0] * 130, 0).back == "snow"
    given = {**base, "scene_data": {"backdrop": "market"}}
    assert r.Scene(given, 5.0, r.Cast(tmp_path), [1.0] * 130, 0).back == "market"  # the script's own choice wins
    bad = {**base, "scene_data": {"backdrop": "volcano"}}
    assert r.Scene(bad, 5.0, r.Cast(tmp_path), [1.0] * 130, 0).back == "hall"  # unknown value is ignored

def _cal(tmp_path, data, narration="The coup works. On 9 November 1799, the Directory falls.", dur=8.0):
    seg = {"scene": "calendar", "narration": narration, "chapter": "Eighteenth of Brumaire", "cast": [],
           "scene_data": data}
    return r.Scene(seg, dur, r.Cast(tmp_path), [1.0] * int(dur * r.FPS), 0)


def _red(img, box):
    px = img.crop(box).convert("RGB").getdata()
    return sum(1 for (a, b, c) in px if a > 170 and b < 90 and c < 90)


def test_calendar_without_a_day_count_shows_the_date_and_no_crossed_boxes_or_question_mark(tmp_path):
    page = _cal(tmp_path, {"title": "The Directory falls"}).frame(7.0)
    assert page.size == (r.W, r.H)
    assert _red(page, (1000, 480, 1280, 720)) == 0  # no "?"
    days = _cal(tmp_path, {"title": "x", "days": 7}).frame(7.0)
    assert _red(days, (1000, 480, 1280, 720)) == 0  # crossed days, but no "?" unless the script asks
    asked = _cal(tmp_path, {"title": "x", "days": 7, "question": True}).frame(7.5)
    assert _red(asked, (1000, 480, 1280, 720)) > 200


def test_a_long_title_shrinks_or_wraps_to_stay_inside_its_banner():
    long = "How the Directory fell and three consuls took over the whole of France in a single day"
    plain, spilled = r.backdrop("parchment").copy(), r.backdrop("parchment").copy()
    r.banner(spilled, long, 90, width=700)
    outside = (0, 0, 280, 220)  # left of the 700px banner (it starts at x=290)
    assert spilled.crop(outside).tobytes() == plain.crop(outside).tobytes()  # no text ran past the box
    x0, x1 = spilled.crop((290, 30, 990, 150)).convert("L").getextrema()
    assert x0 < 100  # the title is drawn inside it

def test_a_cast_scene_is_written_into_a_folder_that_does_not_exist_yet(tmp_path):
    out = tmp_path / "projects" / "9" / "cast" / "cast_001.mp4"
    seg = {"scene": "title", "scene_data": {"title": "Hello"}, "cast": []}
    assert r.render_scene(seg, 1.0, out, out.parent) == out and out.exists() and out.stat().st_size > 0


def test_a_long_title_card_stays_inside_the_picture(tmp_path):
    seg = {"scene": "title", "scene_data": {"title": "Who started the fires? Disputed."}, "cast": []}
    img = r.Scene(seg, 5.0, r.Cast(tmp_path), [1.0] * 130, 0).frame(4.0)
    light = img.convert("L").point(lambda v: 255 if v > 200 else 0)  # the cream title text
    assert light.crop((0, 0, 6, r.H)).getbbox() is None and light.crop((r.W - 6, 0, r.W, r.H)).getbbox() is None
    assert light.getbbox() is not None

def test_map_labels_of_close_places_do_not_overlap_and_stay_in_frame():
    f = r.font(36)
    xy = [(500.0, 300.0), (520.0, 310.0), (545.0, 305.0), (60.0, 160.0)]
    boxes = r._label_boxes(xy, ["Niemen", "Smolensk", "Moscow", "Paris"], f)
    for i, a in enumerate(boxes):
        assert a[0] >= 20 and a[2] <= r.W - 20 and a[1] >= 140 and a[3] <= r.H - 20
        for b in boxes[:i]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_the_narrator_stands_below_the_diagram_boxes(tmp_path):
    seg = {"scene": "diagram", "cast": ["A"], "scene_data": {"title": "T", "steps": ["One", "Two", "Three", "Four"]},
           "narration": "x"}
    img = r.Scene(seg, 8.0, r.Cast(tmp_path), [0.0] * 300, 0).frame(7.0)
    dark = img.crop((100, 255, 330, 495)).convert("L").point(lambda v: 255 if v < 70 else 0)
    # the first step box region holds only its own text: no big dark sprite block (hat, coat) in front of it
    assert dark.getbbox() is None or (dark.getbbox()[3] - dark.getbbox()[1]) < 200 and dark.histogram()[255] < 6000


def test_palm_trees_only_on_the_desert_backdrop():
    assert r.guess_backdrop("a camp in the Sahara desert near Carthage") == "desert"
    assert r.guess_backdrop("a Madrid square") == "market"
    from PIL import ImageChops
    box = (100, 100, 300, 380)  # where the left palm stands
    diff = ImageChops.difference(r.backdrop("market").crop(box), r.backdrop("desert").crop(box)).convert("L")
    assert diff.getbbox() is not None and sum(diff.histogram()[40:]) > 500  # the desert has trees there, the market not

def test_the_narrator_is_not_drawn_as_a_talking_character(tmp_path):
    """Only a skit line moves a figure's mouth; narration over a title, map, calendar or speechless skit does not."""
    for kind in ("title", "calendar", "diagram", "skit"):
        seg = {"scene": kind, "cast": ["Odo"], "scene_data": {"title": "T", "days": 3, "steps": ["a", "b"]}, "narration": "x"}
        loud = r.Scene(seg, 6.0, r.Cast(tmp_path), [1.0] * 200, 0).frame(3.3)
        quiet = r.Scene(seg, 6.0, r.Cast(tmp_path), [0.0] * 200, 0).frame(3.3)
        assert loud.tobytes() == quiet.tobytes(), kind

def test_diagram_steps_show_every_word_inside_their_box(tmp_path):
    steps = ["Here is how", "One, loot from conquered land", "Two, taxes from the farms", "Three, trade across the sea",
             "Picture a bathtub"]
    cw, _ = r.diagram_layout(len(steps))
    for text in steps:
        size, lines = r.diagram_text(text, cw)
        assert " ".join(lines).split() == text.split()  # nothing dropped
        assert all(r.font(size).getlength(ln) <= cw - 30 for ln in lines) and len(lines) <= 4
    seg = {"scene": "diagram", "cast": [], "scene_data": {"title": "T", "steps": steps}, "narration": "x"}
    assert r.Scene(seg, 8.0, r.Cast(tmp_path), [0.0] * 300, 0).frame(7.5).size == (r.W, r.H)


def test_a_calendar_without_a_date_does_not_show_its_title_twice(tmp_path):
    seg = {"scene": "calendar", "chapter": "Bread, Games and 100 Days", "narration": "Rome keeps the crowd happy.",
           "scene_data": {"title": "Bread, Games and 100 Days"}, "cast": []}
    dated = {**seg, "narration": "On 9 November 1799 it ends."}
    cast = r.Cast(tmp_path)
    undated_img = r.Scene(seg, 8.0, cast, [0.0] * 300, 0).frame(7.0)
    dated_img = r.Scene(dated, 8.0, cast, [0.0] * 300, 0).frame(7.0)
    zone = (300, 30, 980, 130)  # where the banner sits
    assert undated_img.crop(zone).convert("L").getextrema()[0] > 120  # parchment only: no banner
    assert dated_img.crop(zone).convert("L").getextrema()[0] < 100  # a dated page keeps its banner text


def test_counter_chip_and_cliffhanger_strip_are_drawn_and_move_the_camera_to_a_wide_shot(tmp_path):
    base = {"scene": "skit", "cast": ["A", "B"], "narration": "x", "speech": [{"who": "A", "text": "Hi."}]}
    cast = r.Scene(base, 8.0, r.Cast(tmp_path), [0.0] * 300, 0)
    plain = cast.frame(2.0)
    with_chip = r.Scene({**base, "scene_data": {"counter": {"n": 1, "of": 3, "label": "Decision"}}}, 8.0,
                        r.Cast(tmp_path), [0.0] * 300, 0).frame(2.0)
    assert plain.crop((60, 130, 330, 200)).tobytes() != with_chip.crop((60, 130, 330, 200)).tobytes()  # the chip
    cliff = r.Scene({**base, "scene_data": {"cliff": "But who will stop him?"}}, 8.0, r.Cast(tmp_path), [0.0] * 300, 0)
    assert cliff.frame(7.5).crop((170, 560, 1110, 700)).tobytes() != plain.crop((170, 560, 1110, 700)).tobytes()
    assert cliff.camera(7.5)[0] < 1.2  # no close-up while the strip is up


def test_every_scene_kind_moves_at_least_every_few_seconds(tmp_path):
    for kind in ("title", "calendar", "easel", "silhouette", "archive", "diagram", "skit"):
        seg = {"scene": kind, "cast": ["A"], "narration": "x", "scene_data": {"title": "T", "items": ["a", "b"],
               "steps": ["a", "b"]}}
        sc = r.Scene(seg, 12.0, r.Cast(tmp_path), [0.0] * 400, 0)
        zooms = [sc.camera(t / 10)[0] for t in range(0, 120)]
        assert max(zooms) - min(zooms) > 0.02, kind  # a beat, not a still
        assert max(zooms) <= max(r.MAX_ZOOM.get(kind, r.DEFAULT_MAX_ZOOM), 1.4 if kind == "skit" else 0) + 1e-6, kind


def test_counter_chip_and_strip_stay_inside_the_zoomed_picture_and_clear_of_the_map_names(tmp_path):
    from studio.history import scene_check as sc
    for kind in ("diagram", "easel", "title", "calendar", "map"):
        seg = {"scene": kind, "cast": [], "narration": "x", "scene_data": {
            "title": "T", "steps": ["a", "b", "c"], "items": ["a"], "region": "europe",
            "points": [{"label": "Paris"}], "counter": {"n": 2, "of": 3, "label": "Decision"},
            "cliff": "Will he reach Moscow?"}}
        scene = r.Scene(seg, 8.0, r.Cast(tmp_path), [0.0] * 300, 0)
        with sc.record_text() as items:
            scene.frame(7.5)
        zoom = r.MAX_ZOOM.get(kind, r.DEFAULT_MAX_ZOOM)
        assert sc.text_problems(items, zoom=zoom) == [], kind


def test_the_map_caption_gives_way_to_the_strip_and_the_chip_hides_in_close_ups(tmp_path):
    from studio.history import scene_check as sc
    seg = {"scene": "map", "cast": [], "narration": "x", "scene_data": {"region": "europe", "title": "T",
           "points": [{"label": "Paris"}], "cliff": "Will he reach Moscow?"}}
    scene = r.Scene(seg, 8.0, r.Cast(tmp_path), [0.0] * 300, 0)
    with sc.record_text() as early:
        scene.frame(1.0)
    with sc.record_text() as late:
        scene.frame(7.5)
    assert any(text == "Approximate map" for text, _ in early)
    assert not any(text == "Approximate map" for text, _ in late)  # the strip has the corner now
    skit = {"scene": "skit", "cast": ["A", "B"], "narration": "x", "speech": [{"who": "A", "text": "Hi."}]}
    plain = r.Scene(skit, 12.0, r.Cast(tmp_path), [0.0] * 400, 0)
    chip = r.Scene({**skit, "scene_data": {"counter": {"n": 1, "of": 3, "label": "D"}}}, 12.0, r.Cast(tmp_path),
                   [0.0] * 400, 0)
    close = next(t / 10 for t in range(0, 120) if chip.camera(t / 10)[0] > 1.25)
    assert plain.frame(close).tobytes() == chip.frame(close).tobytes()  # nothing drawn over the speech bubble


def test_skit_layouts_vary_from_skit_to_skit_and_keep_figures_and_bubbles_in_frame(tmp_path):
    segs = [{"scene": "skit"}, {"scene": "map"}, {"scene": "skit"}, {"scene": "skit", "scene_data": {"layout": "stagger"}},
            {"scene": "skit"}, {"scene": "skit"}, {"scene": "skit"}, {"scene": "skit"}]
    got = r.assign_layouts(segs)
    skits = [got[i] for i in sorted(got)]
    assert all(a != b for a, b in zip(skits, skits[1:])) and got[3] == "stagger" and len(set(skits)) >= 4
    for layout in r.LAYOUTS:
        for n in (1, 2, 3, 4):
            for cx, feet, size in r.skit_places(layout, n):
                assert size / 2 < cx < r.W - size / 2 and feet - size * 0.94 > 150 and feet < r.H + 40, (layout, n)
    base = {"scene": "skit", "cast": ["A", "B"], "narration": "x", "speech": [{"who": "B", "text": "Hi there."}]}
    frames = {lay: r.Scene({**base, "_layout": lay}, 10.0, r.Cast(tmp_path), [0.0] * 300, 0).frame(8.0).tobytes()
              for lay in r.LAYOUTS}
    assert len(set(frames.values())) == len(r.LAYOUTS)  # every layout looks different
