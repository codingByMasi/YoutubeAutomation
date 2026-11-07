"""Retention review: hook, counted promises, still cards, jokes, cliffhangers and peaks, for any video."""
from studio.quality import retention_review as rr


def seg(text, scene="skit", sec=10.0, **kw):
    return {"narration": text, "scene": scene, "est_seconds": sec, "chapter": kw.pop("chapter", "c"), **kw}


def test_an_uncounted_promise_is_reported_and_counting_it_out_clears_it():
    hook = seg("Ten years. Three decisions did it. By the end you will know which.", sec=9)
    body = [seg("The blockade.", chapter="a"), seg("Then Spain.", chapter="b"), seg("Then Russia.", chapter="c")]
    probs = rr.uncounted_promise([hook, *body])
    assert probs and "three decisions" in probs[0]["issue"].lower() and "scene_data.counter" in probs[0]["fix"]
    counted = [hook, seg("Decision one: the blockade."), seg("Decision two: Spain."), seg("Decision three: Russia.")]
    assert rr.uncounted_promise(counted) == []
    chips = [hook, *[seg("x", scene_data={"counter": {"n": k, "of": 3, "label": "Decision"}}) for k in (1, 2, 3)]]
    assert rr.uncounted_promise(chips) == []
    assert rr.uncounted_promise([seg("How does it work? Find out.")]) == []  # no countable promise: nothing to count
    five = [seg("Here are five reasons it failed."), seg("First, money."), seg("Second, people.")]
    assert "2 of 5" in rr.uncounted_promise(five)[0]["issue"]


def test_the_first_thirty_seconds_flag_a_still_hook_and_backstory_after_it():
    segs = [seg("Hook line?", scene="title", sec=9), seg("Go back to 1769, when he was born.", scene="map", sec=12),
            seg("Then more.", scene="skit", sec=15)]
    ids = {i["id"] for i in rr.weak_start(segs)}
    assert ids == {"hook_card", "backstory_first"}
    good = [seg("Hook line?", sec=9), seg("He lifts the crown himself.", scene="skit", sec=12),
            seg("Then 1769, but later.", scene="map", sec=15)]
    good[1]["est_seconds"] = 25  # the dated map starts after the first 30 seconds
    assert rr.weak_start(good) == []  # a date after the first 30 s, or in a skit, is fine


def test_long_still_cards_and_flat_skits_are_reported():
    segs = [seg("a", scene="calendar", sec=14), seg("b", scene="title", sec=4), seg("c", scene="easel", sec=11),
            seg("d", speech=[{"who": "A", "text": "x"}]), seg("e", speech=[{"who": "A", "text": "x"}]),
            seg("f", speech=[{"who": "A", "text": "x"}, {"who": "B", "text": "y"}, {"who": "A", "text": "z"}])]
    assert rr.long_cards(segs)[0]["segments"] == [1, 3]
    assert rr.flat_skits(segs)[0]["segments"] == [4, 5]
    ok = [seg("a", scene="title", sec=5)] + [seg(str(i), speech=[{"who": "A", "text": "x"}, {"who": "B", "text": "y"}])
                                              for i in range(3)]
    assert rr.long_cards(ok) == [] and rr.flat_skits(ok) == []


def test_cliffhangers_and_the_emotional_peak():
    chapters = [seg("Flat.", chapter=str(i)) for i in range(6)]
    assert rr.no_cliffhangers(chapters)
    ends = [seg("What happens next?", chapter=str(i)) for i in range(6)]
    assert rr.no_cliffhangers(ends) == []
    cliff = [seg("Flat.", chapter=str(i), scene_data={"cliff": "Who stops him?"}) for i in range(6)]
    assert rr.no_cliffhangers(cliff) == []
    segs = [seg("x") for _ in range(10)]
    assert rr.no_peak(segs)
    segs[7] = seg("The cost.", scene="silhouette", sec=14, emotion="warm")
    assert rr.no_peak(segs) == []


def test_review_scores_and_qa_and_the_app_report_carry_it():
    from studio.stages.qa import quality_report
    segs = [seg("Ten years. Three decisions. Which?", scene="title", sec=8)] + \
        [seg("Go back to 1769.", scene="calendar", sec=12, chapter=str(i)) for i in range(6)]
    rev = rr.review({"segments": segs})
    assert rev["score"] < 8 and {i["id"] for i in rev["items"]} >= {"uncounted_promise", "hook_card", "long_cards"}
    rep = quality_report({"segments": segs})
    assert rep["retention"]["score"] == rev["score"] and any(w.startswith("Retention:") for w in rep["warnings"])


def test_a_missing_narrator_and_untagged_skits_are_reported():
    segs = [seg("a", scene="skit") for _ in range(4)]
    items = {i["id"]: i for i in rr.review({"segments": segs})["items"]}
    assert "no_narrator" in items and "narrator" in items["no_narrator"]["fix"]
    assert "no_places" in items and items["no_places"]["segments"] == [1, 2, 3, 4]
    tagged = [seg("a", scene="skit", scene_data={"place": "Paris, 1804"}) for _ in range(4)]
    ids = {i["id"] for i in rr.review({"narrator": "Storyteller", "segments": tagged})["items"]}
    assert "no_narrator" not in ids and "no_places" not in ids
    assert rr.no_narrator({"segments": []}, [seg("a", scene=None)]) == []  # a video with no drawn scenes needs none
