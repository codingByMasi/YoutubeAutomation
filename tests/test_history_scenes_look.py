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


def test_palm_trees_only_on_the_desert_backdrop():
    assert r.guess_backdrop("a camp in the Sahara desert near Carthage") == "desert"
    assert r.guess_backdrop("a Madrid square") == "market"
    from PIL import ImageChops
    box = (100, 100, 300, 380)  # where the left palm stands
    diff = ImageChops.difference(r.backdrop("market").crop(box), r.backdrop("desert").crop(box)).convert("L")
    assert diff.getbbox() is not None and sum(diff.histogram()[40:]) > 500  # the desert has trees there, the market not
