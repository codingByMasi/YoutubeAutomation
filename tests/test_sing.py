"""Optional sung melody (OpenUtau): melody plan, MIDI/USTX files, vocal pickup, mixing and the fallback.

OpenUtau itself is never run (it is a GUI app on the owner's PC); a generated WAV stands in for its export.
"""

from __future__ import annotations

import json
import shutil
import struct
import wave
from pathlib import Path

import pytest
from typer.testing import CliRunner

from studio import cli
from studio.errors import StudioError
from studio.kids import demo, music, openutau, sing, sing_files, sing_mix, sing_step

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "kids_sample.json").read_text())


@pytest.mark.parametrize("word,n", [("duck", 1), ("little", 2), ("hope", 1), ("jumped", 1), ("banana", 3),
                                    ("one", 1), ("...", 0)])
def test_syllables(word: str, n: int) -> None:
    assert sing.syllables(word) == n


def test_line_notes_use_plus_for_extra_syllables() -> None:
    notes = sing.line_notes("Little duck")
    assert [n["lyric"] for n in notes] == ["Little", "+", "duck"]


def test_same_line_same_tune_and_in_range() -> None:
    a, b = sing.line_notes("Five little ducks"), sing.line_notes("five little ducks")
    assert [n["tone"] for n in a] == [n["tone"] for n in b]
    assert all(60 <= n["tone"] <= 60 + 12 + 9 for n in a)


def test_plan_repeats_chorus_and_ends_on_root() -> None:
    plan = sing.build_plan(SAMPLE)
    chorus = [i for i, s in enumerate(SAMPLE["scenes"]) if s["kind"] == "chorus"]
    assert len(chorus) >= 2
    marks = plan["scenes"]
    first = [n["tone"] for n in plan["notes"] if marks[chorus[0]]["start_beat"] <= n["start_beat"] <
             marks[chorus[0] + 1]["start_beat"]]
    second_end = marks[chorus[1] + 1]["start_beat"] if chorus[1] + 1 < len(marks) else plan["total_beats"]
    second = [n["tone"] for n in plan["notes"] if marks[chorus[1]]["start_beat"] <= n["start_beat"] < second_end]
    assert first[:-1] == second[:-1]  # the last chorus ends on the home note
    assert plan["notes"][-1]["tone"] == sing.ROOT_MIDI
    starts = [n["start_beat"] for n in plan["notes"]]
    assert starts == sorted(starts) and plan["total_s"] > 10


def test_midi_is_well_formed(tmp_path: Path) -> None:
    plan = sing.build_plan(SAMPLE)
    data = sing_files.midi_bytes(plan)
    assert data[:4] == b"MThd" and struct.unpack(">IHHH", data[4:14]) == (6, 0, 1, sing.PPQ)
    assert data[14:18] == b"MTrk"
    assert struct.unpack(">I", data[18:22])[0] == len(data) - 22
    assert data.count(b"\x90") >= len(plan["notes"])  # one note-on per note (data bytes may repeat the value)
    assert data.endswith(b"\xff\x2f\x00")


def test_ustx_lists_every_note() -> None:
    plan = sing.build_plan(SAMPLE)
    text = sing_files.ustx_text(plan)
    assert text.count("    lyric:") == len(plan["notes"])
    assert "bpm: 104" in text and "resolution: 480" in text and "singer" not in text


def test_sing_step_is_idempotent_and_needs_a_script(make_ctx) -> None:
    ctx = make_ctx()
    with pytest.raises(StudioError, match="No script"):
        sing_step.run(ctx, "nothing")
    d = ctx.settings.root / "projects" / "kids_ducks" if hasattr(ctx.settings, "root") else None
    from studio.kids.script import project_dir
    d = project_dir(ctx, "ducks")
    d.mkdir(parents=True, exist_ok=True)
    (d / "script.json").write_text(json.dumps(SAMPLE))
    files = sing_step.run(ctx, "ducks")
    assert all(p.exists() for p in files.values())
    stamp = files["ustx"].stat().st_mtime_ns
    sing_step.run(ctx, "ducks")
    assert files["ustx"].stat().st_mtime_ns == stamp
    assert "No exported vocal" in sing_step.status(ctx, "ducks")


def test_vocal_pickup_and_import(tmp_path: Path) -> None:
    assert openutau.vocal_path(tmp_path) is None
    with pytest.raises(StudioError, match="No sung vocal"):
        openutau.import_vocal(tmp_path)
    (tmp_path / "Export").mkdir()
    old, new = tmp_path / "Export" / "a.wav", tmp_path / "Export" / "b.wav"
    old.write_bytes(b"1")
    new.write_bytes(b"2")
    import os
    os.utime(old, (1, 1))
    assert openutau.vocal_path(tmp_path) == new
    assert openutau.import_vocal(tmp_path).read_bytes() == b"2"
    assert openutau.vocal_path(tmp_path) == tmp_path / "vocal.wav"


def test_find_openutau_configured(tmp_path: Path) -> None:
    exe = tmp_path / "OpenUtau.exe"
    exe.write_bytes(b"")
    assert openutau.find_openutau(str(exe)) == exe
    assert openutau.find_openutau(str(tmp_path / "missing.exe")) is None


def test_mix_command_stretches_within_limits() -> None:
    cmd, note = sing_mix.sung_mix_cmd(Path("v.mp4"), Path("b.wav"), Path("s.wav"), Path("o.mp4"), 60.0, 66.0)
    assert "atempo=1.1000" in " ".join(cmd) and note == ""
    cmd, note = sing_mix.sung_mix_cmd(Path("v.mp4"), Path("b.wav"), Path("s.wav"), Path("o.mp4"), 30.0, 120.0)
    assert "atempo=1.5000" in " ".join(cmd) and "Sung vocal is 120s" in note


def test_bed_has_no_melody() -> None:
    assert len(music.score("t", melody=False)) < len(music.score("t"))


def _sine(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x10\x20" * int(22050 * seconds))


def test_build_falls_back_without_vocal_and_mixes_with_it(make_ctx) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    ctx = make_ctx()
    out = demo.run(ctx)
    assert not (out.parent / "music_bed.wav").exists()  # no vocal: the normal tune path was used
    assert (out.parent / "music.wav").exists()
    (out.parent / "sung").mkdir()
    _sine(out.parent / "sung" / "vocal.wav", 8.0)
    out2 = demo.run(ctx, force=True)
    assert (out2.parent / "music_bed.wav").exists() and out2.stat().st_size > 10_000


def test_cli_sing_writes_files_and_reports_missing_vocal(make_ctx, monkeypatch) -> None:
    ctx = make_ctx()
    monkeypatch.setattr(cli, "_ctx", lambda: ctx)
    from studio.kids.script import project_dir, slugify
    d = project_dir(ctx, slugify("ducks"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "script.json").write_text(json.dumps(SAMPLE))
    res = CliRunner().invoke(cli.app, ["kids", "sing", "ducks", "--open"])
    assert res.exit_code == 0, res.output
    assert (d / "sung" / "song.ustx").exists()
    assert "OpenUtau not found" in res.output and "No exported vocal" in res.output
    wav = d / "x.wav"
    _sine(wav, 1.0)
    res = CliRunner().invoke(cli.app, ["kids", "sing", "ducks", "--use", str(wav)])
    assert "Vocal ready" in res.output and (d / "sung" / "vocal.wav").exists()
