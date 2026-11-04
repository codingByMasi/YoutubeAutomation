"""Characters speak their own lines in their own voices; the mix ducks the narrator."""
import subprocess

from studio.history import speech_audio as sa
from studio.util import ffmpeg as ff


def _tone(path, secs, freq=300):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}",
                    "-ar", "48000", "-ac", "1", str(path)], check=True)


class _S:
    tts_provider = "edge"


def test_roster_and_figures_get_stable_distinct_voices():
    assert sa.voice_for("quill")["kokoro"] == "bm_george"
    assert sa.voice_for("Captain Blunder") == sa.voice_for("blunder")
    assert sa.voice_for("Hannibal") == sa.voice_for("Hannibal")
    assert sa.voice_for("blunder")["kokoro"] != sa.voice_for("dash")["kokoro"]


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
    segs = [{"scene": "skit", "speech": [{"who": "dash", "text": "Hello there."}]}]
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
    segs = [{"scene": "skit", "speech": [{"who": "dash", "text": "News!"}, {"who": "vex", "text": "Quiet."}]},
            {"scene": "map", "speech": []}]
    assert sa.synth_lines(_S(), tmp_path, segs, lambda m: None) == 2
    assert used == [sa.voice_for("dash")["kokoro"], sa.voice_for("vex")["kokoro"]]
    assert all(abs(x["seconds"] - 0.8) < 0.2 and x["audio"] for x in segs[0]["speech"])


def test_mix_adds_lines_and_keeps_length(tmp_path):
    nar = tmp_path / "n.wav"
    _tone(nar, 6.0, 200)
    line = tmp_path / "l.wav"
    _tone(line, 1.0, 800)
    segs = [{"scene": "skit", "speech": [{"who": "dash", "text": "x", "audio": str(line), "seconds": 1.0}]}]
    out = sa.mix_into_narration(nar, segs, [(0.0, 6.0)], tmp_path / "m.wav")
    assert out != nar and abs(ff.probe_duration(out) - 6.0) < 0.2
    assert sa.mix_into_narration(nar, [{"scene": "map"}], [(0.0, 6.0)], tmp_path / "m2.wav") == nar


def test_narrator_is_silent_while_a_character_speaks(tmp_path):
    import numpy as np
    nar, line = tmp_path / "n.wav", tmp_path / "l.wav"
    _tone(nar, 6.0, 200)
    _tone(line, 1.0, 800)
    segs = [{"scene": "skit", "speech": [{"who": "dash", "text": "x", "audio": str(line), "seconds": 1.0}]}]
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
