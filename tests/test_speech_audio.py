"""Characters speak their own lines in their own voices; the mix ducks the narrator."""
import subprocess

from studio.history import speech_audio as sa
from studio.util import ffmpeg as ff


def _tone(path, secs, freq=300):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}",
                    "-ar", "48000", "-ac", "1", str(path)], check=True)


class _S:
    tts_provider = "edge"


def test_figures_get_stable_voices_and_described_ones_follow_their_description():
    assert sa.voice_for("Hannibal") == sa.voice_for("Hannibal")
    assert sa.voice_for("Dusty")  # an old script's name still gets a voice, no crash
    old = sa.voice_for("Hasdrubal", [{"name": "Hasdrubal", "gender": "male", "age": "elder"}])
    assert old["speed"] == 0.9


def test_line_times_follow_real_lengths_and_fit_the_scene():
    sp = [{"seconds": 1.5}, {"seconds": 2.0}]
    t = sa.line_times(sp, 10.0)
    assert t[0] == sa.LEAD and t[1] >= t[0] + 1.5
    tight = sa.line_times([{"seconds": 3.0}, {"seconds": 3.0}], 7.0)
    assert tight[1] >= tight[0] + 3.0  # lines never overlap, gaps just shrink
    assert sa.line_times([{}, {}], 10.0) == [0.5, 4.9]  # no audio yet: even spacing as before
    assert sa.line_times([], 5.0) == []


def test_silent_provider_voices_nothing(tmp_path):
    class Silent:
        tts_provider = "silent"
    segs = [{"scene": "skit", "speech": [{"who": "Hannibal", "text": "Hello there."}]}]
    assert sa.synth_lines(Silent(), tmp_path, segs, lambda m: None) == 0 and "audio" not in segs[0]["speech"][0]


def test_synth_uses_each_characters_voice(tmp_path, monkeypatch):
    used = []

    class Fake:
        name = "fake"

        def __init__(self, voice):
            self.voice = voice

        def synth(self, text, out, prosody=None, **_):
            used.append(self.voice)
            _tone(out.with_suffix(".wav"), 0.8)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out.with_suffix(".wav")), str(out)], check=True)
            return out

    monkeypatch.setattr(sa, "_engines", lambda settings, v: [Fake(v["kokoro"])])
    segs = [{"scene": "skit", "speech": [{"who": "Hannibal", "text": "News!"}, {"who": "Scipio", "text": "Quiet."}]},
            {"scene": "map", "speech": []}]
    assert sa.synth_lines(_S(), tmp_path, segs, lambda m: None) == 2
    assert used == [sa.voice_for("Hannibal")["kokoro"], sa.voice_for("Scipio")["kokoro"]]
    assert all(abs(x["seconds"] - 0.8) < 0.2 and x["audio"] for x in segs[0]["speech"])


def test_mix_adds_lines_and_keeps_length(tmp_path):
    nar = tmp_path / "n.wav"
    _tone(nar, 6.0, 200)
    line = tmp_path / "l.wav"
    _tone(line, 1.0, 800)
    segs = [{"scene": "skit", "speech": [{"who": "Hannibal", "text": "x", "audio": str(line), "seconds": 1.0}]}]
    out = sa.mix_into_narration(nar, segs, [(0.0, 6.0)], tmp_path / "m.wav")
    assert out != nar and abs(ff.probe_duration(out) - 6.0) < 0.2
    assert sa.mix_into_narration(nar, [{"scene": "map"}], [(0.0, 6.0)], tmp_path / "m2.wav") == nar


def test_mix_stays_stereo_and_centred(tmp_path):
    nar, line = tmp_path / "n.wav", tmp_path / "l.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=6",
                    "-ar", "48000", "-ac", "2", str(nar)], check=True)
    _tone(line, 1.0, 800)
    segs = [{"scene": "skit", "speech": [{"who": "Hannibal", "text": "x", "audio": str(line), "seconds": 1.0}]}]
    out = sa.mix_into_narration(nar, segs, [(0.0, 6.0)], tmp_path / "m.wav")
    chans = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=channels",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout
    assert chans.strip() == "2"  # a mono mix made the intro+main join play on the left channel only


def test_narrator_is_silent_while_a_character_speaks(tmp_path):
    import numpy as np
    nar, line = tmp_path / "n.wav", tmp_path / "l.wav"
    _tone(nar, 6.0, 200)
    _tone(line, 1.0, 800)
    segs = [{"scene": "skit", "speech": [{"who": "Hannibal", "text": "x", "audio": str(line), "seconds": 1.0}]}]
    out = sa.mix_into_narration(nar, segs, [(0.0, 6.0)], tmp_path / "m.wav")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "s16le", "-ac", "1", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(float)

    def level(t0, t1, hz):  # strength of one frequency in a time window
        w = x[int(t0 * 48000):int(t1 * 48000)]
        return abs(np.sum(w * np.exp(-2j * np.pi * hz * np.arange(len(w)) / 48000))) / len(w)
    a = sa.line_times(segs[0]["speech"], 6.0)[0]
    assert level(a + 0.2, a + 0.8, 800) > 100  # the character is heard
    assert level(a + 0.2, a + 0.8, 200) < 5  # the narrator is not
    assert level(4.0, 5.5, 200) > 100  # narrator back after the line


def test_make_room_plays_the_narration_first_then_a_short_exchange_and_is_repeatable():
    segs = [{"scene": "skit", "real_seconds": 4.0,
             "speech": [{"audio": "a.mp3", "seconds": 2.0}, {"audio": "b.mp3", "seconds": 1.5}]},
            {"scene": "map", "real_seconds": 5.0, "speech": []}]
    assert sa.make_room(segs) == 1
    at, seg = segs[0]["lines_at"], segs[0]
    assert at == round(4.0 + sa.PAUSE, 3) and seg["lead_seconds"] == 0  # narration from second 0, uncut
    assert seg["real_seconds"] == round(at + 3.5 + sa.GAP + 0.3, 3) and segs[1]["real_seconds"] == 5.0
    sa.make_room(segs)  # running visuals again must not grow the segment twice
    assert seg["real_seconds"] == round(at + 3.5 + sa.GAP + 0.3, 3)
    seg["real_seconds"] = 6.0  # the voice stage re-ran with a new narration length
    sa.make_room(segs)
    assert seg["narr_seconds"] == 6.0 and seg["lines_at"] == round(6.0 + sa.PAUSE, 3)
    for t, line in zip(sa.line_times(seg["speech"], seg["real_seconds"], seg["lines_at"]), seg["speech"], strict=True):
        assert t >= seg["narr_seconds"] and t + line["seconds"] <= seg["real_seconds"]  # after the narrator


def test_make_room_keeps_the_dialogue_short_and_converts_an_older_lines_first_layout():
    long = [{"audio": f"{k}.mp3", "seconds": 2.5} for k in range(5)]
    segs = [{"scene": "skit", "real_seconds": 4.0, "speech": long}]
    sa.make_room(segs)
    assert len(segs[0]["speech"]) == 2  # 2.5 + gap + 2.5 fits the budget; a third line does not
    old = [{"scene": "skit", "real_seconds": 15.0, "narr_seconds": 3.0, "lead_seconds": 12.0,
            "speech": [{"audio": "a.mp3", "seconds": 2.0}]}]
    sa.make_room(old)
    assert old[0]["lines_at"] == round(3.0 + sa.PAUSE, 3) and old[0]["lead_seconds"] == 0
    assert old[0]["real_seconds"] == round(3.4 + 2.0 + 0.3, 3)


def test_mix_puts_the_lines_after_the_narration(tmp_path):
    import numpy as np
    nar, line = tmp_path / "n.wav", tmp_path / "l.wav"
    _tone(nar, 4.7, 200)  # the build pads the narration to the segment length
    _tone(line, 1.0, 800)
    seg = {"scene": "skit", "lines_at": 3.4, "speech": [{"who": "A", "text": "x", "audio": str(line), "seconds": 1.0}]}
    out = sa.mix_into_narration(nar, [seg], [(0.0, 4.7)], tmp_path / "m.wav")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "s16le", "-ac", "1", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(float)

    def level(t0, t1, hz):
        w = x[int(t0 * 48000):int(t1 * 48000)]
        return abs(np.sum(w * np.exp(-2j * np.pi * hz * np.arange(len(w)) / 48000))) / len(w)
    assert level(0.2, 2.8, 200) > 100 and level(0.2, 2.8, 800) < 5  # the narrator alone, from the start
    assert level(3.6, 4.3, 800) > 100 and level(3.6, 4.3, 200) < 5  # then the character


def test_fit_voice_delays_the_narration_by_the_lead(tmp_path):
    from studio.stages.build import fit_voice_cmd
    cmd = fit_voice_cmd(tmp_path / "v.mp3", 10.0, tmp_path / "o.wav", 4.0)
    assert "adelay=4000:all=1,apad,atrim=end=10.000" in cmd[cmd.index("-af") + 1]
    assert "adelay" not in fit_voice_cmd(tmp_path / "v.mp3", 10.0, tmp_path / "o.wav")[5]
