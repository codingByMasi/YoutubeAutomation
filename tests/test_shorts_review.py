"""Every Short is reviewed like the main video; a failing run is replaced by the next-best one."""
import subprocess

from studio.quality import shorts_review as sr

GOOD = {"duration": 30.0, "lufs": -14.0, "true_peak": -1.5, "silences": [], "first_sound": 0.0, "longest_still": 0.5,
        "moving_share": 0.9}
ASS_OK = "Style: Banner\nDialogue: 1,0:00:00.00,0:00:02.80,Banner,,0,0,0,, WHAT COULD GO WRONG? \n" \
         "Dialogue: 0,0:00:00.10,0:00:00.40,Default,,0,0,0,,THE COUP WORKS\n"


def seg(scene="skit", **kw):
    return {"scene": scene, "narration": "x", "est_seconds": 12, "chapter": "c", "cast": ["A"], **kw}


def test_a_good_short_passes_and_each_failure_is_named(tmp_path):
    window = [seg(), seg("skit")]
    assert sr.review_short(tmp_path / "s.mp4", window, None, ASS_OK, "What could go wrong?", facts=dict(GOOD))["ok"]

    def bad(**change):
        return sr.review_short(tmp_path / "s.mp4", window, None, ASS_OK, "What could go wrong?",
                               facts={**GOOD, **change})["issues"]
    assert any("14 s" in i or "runs" in i for i in bad(duration=9.0))
    assert any("loudness" in i for i in bad(lufs=-24.0))
    assert any("true peak" in i for i in bad(true_peak=-0.2))
    assert any("silence" in i for i in bad(silences=[2.4]))
    assert any("nothing is heard" in i for i in bad(first_sound=1.4))
    assert any("holds still" in i for i in bad(longest_still=4.0))


def test_opening_on_a_card_or_without_a_title_or_with_wide_captions_fails(tmp_path):
    ok = dict(GOOD)
    card = sr.review_short(tmp_path / "s.mp4", [seg("calendar")], None, ASS_OK, "t", facts=ok)
    assert any("card" in i for i in card["issues"])
    no_title = sr.review_short(tmp_path / "s.mp4", [seg()], None, "Style: Default\n", "", facts=ok)
    assert any("no title" in i for i in no_title["issues"])
    wide = ASS_OK + "Dialogue: 0,0:00:01.00,0:00:01.40,Default,,0,0,0,,WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW\n"
    assert any("wider than the frame" in i for i in sr.review_short(tmp_path / "s.mp4", [seg()], None, wide, "t",
                                                                   facts=ok)["issues"])


def test_measure_reads_a_real_file(tmp_path):
    f = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-shortest", str(f)], check=True)
    m = sr.measure(f)
    assert {"lufs", "true_peak", "silences", "first_sound", "duration", "longest_still", "moving_share"} <= set(m)
    assert abs(m["duration"] - 4.0) < 0.3 and m["moving_share"] > 0.5 and m["silences"] == []
    quiet = tmp_path / "q.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:size=270x480:rate=30:duration=6",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest", str(quiet)], check=True)
    q = sr.measure(quiet)
    assert q["longest_still"] >= 2.5 and q["silences"]  # a still, silent clip is seen as such
