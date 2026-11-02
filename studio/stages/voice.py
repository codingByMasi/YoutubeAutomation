"""`voice`: narration audio per segment; real durations replace estimates."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer

from studio.context import Ctx
from studio.models import Segment
from studio.providers.tts import TTS, get_tts
from studio.stages.base import get_video, run_stage
from studio.stages.script import load_package, pacing_warnings, write_package
from studio.story import narration as nar
from studio.story import profile as sp
from studio.util import progress
from studio.util.ffmpeg import probe_duration

VOICE_WORKERS = 4


def apply_real_durations(pkg: dict, rows: list[Segment], durations: dict[int, float]) -> float:
    """Write real seconds into DB rows and the package; return the new total length in seconds."""
    for row in rows:
        if row.position in durations:
            row.real_seconds = round(durations[row.position], 3)
            pkg["segments"][row.position - 1]["real_seconds"] = row.real_seconds
    return round(sum(float(s.get("real_seconds") or s["est_seconds"]) for s in pkg["segments"]), 3)


def _grp(pkg: dict, prof: dict) -> list[list[int]]:
    return nar.groups(pkg["segments"], prof)


def _voice_chapters(engine, prof: dict, pkg: dict, rows: list[Segment], out: Path, durations: dict,
                    measure: Callable, force: bool) -> float:
    """Synthesize per chapter group (intonation continues), split by word timing, add pauses, keep word times.

    A group whose text, prosody and voice are unchanged is reused from the last run (voice/groups.json)."""
    segs = pkg["segments"]
    groups = nar.groups(segs, prof)
    index_f = out / "groups.json"
    index = json.loads(index_f.read_text(encoding="utf-8")) if index_f.exists() else {}
    use_pro = sp.enabled(prof, "prosody")
    pause_flag = use_pro

    def seg_path(i: int) -> Path:
        return out / f"seg_{i + 1:03d}.mp3"

    def do_group(gi: int) -> tuple[int, dict]:
        idx = groups[gi]
        texts = [segs[i]["narration"] for i in idx]
        pro = nar.prosody_for(prof, nar.emotion_of(segs[idx[0]], idx[0])) if use_pro else None
        pads = {i: (nar.pause_after(prof, segs, i) if pause_flag else 0.0) for i in idx}
        key = nar.group_key(texts + [str(pads)], pro or {}, getattr(engine, "voice", ""), engine.name)
        cached = index.get(key)
        if not force and cached and all(seg_path(i).exists() and seg_path(i).stat().st_size for i in idx):
            return gi, {"key": key, "words": cached["words"], "reused": True}
        tmp = out / f"chap_{gi:02d}.mp3"
        words = engine.synth_timed(" ".join(texts), tmp, pro)
        cuts = nar.split_points(words, texts, 0) if words else None
        if cuts is None:  # no usable word timing: one call per segment (still prosody, still cached)
            sw = []
            for i in idx:
                engine.synth(segs[i]["narration"], seg_path(i))
                sw.append([])
                if pads[i] > 0:
                    nar.ffmpeg_cut(seg_path(i), tmp, 0, None, pads[i])
                    tmp.replace(seg_path(i))
            return gi, {"key": key, "words": sw, "reused": False}
        per = nar.words_per_segment(words, texts, cuts)
        bounds = [0.0, *cuts, None]
        for j, i in enumerate(idx):
            nar.ffmpeg_cut(tmp, seg_path(i), bounds[j], bounds[j + 1], pads[i])
        tmp.unlink(missing_ok=True)
        return gi, {"key": key, "words": [[list(w) for w in ws] for ws in per], "reused": False}

    with typer.progressbar(length=len(groups), label=f"Voicing {len(groups)} chapter groups ({engine.name})") as bar, \
            ThreadPoolExecutor(VOICE_WORKERS) as pool:
        for gi, info in pool.map(do_group, range(len(groups))):
            index[info["key"]] = {"words": info["words"]}
            for j, i in enumerate(groups[gi]):
                segs[i]["words"] = info["words"][j] if j < len(info["words"]) else []
            bar.update(1)
    index_f.write_text(json.dumps(index), encoding="utf-8")
    for row in rows:
        path = seg_path(row.position - 1)
        row.audio_path = str(path)
        durations[row.position] = measure(path)
    return apply_real_durations(pkg, rows, durations)


def run(ctx: Ctx, video_id: int, force: bool = False, tts: TTS | None = None,
        measure: Callable = probe_duration) -> None:
    s = ctx.session
    video = get_video(s, video_id)

    def work() -> None:
        from studio import production
        engine = tts or get_tts(production.apply(ctx.settings, video_id))
        out = ctx.settings.project_dir(video_id) / "voice"
        out.mkdir(exist_ok=True)
        pkg = load_package(ctx, video_id)
        rows = s.query(Segment).filter_by(video_id=video_id).order_by(Segment.position).all()
        durations = {}
        prof = sp.for_channel(ctx.settings.root)
        if sp.enabled(prof, "chapter_tts") and hasattr(engine, "synth_timed") and pkg.get("engine"):
            total = _voice_chapters(engine, prof, pkg, rows, out, durations, measure, force)
            write_package(ctx, video_id, pkg)
            typer.echo(f"Narration: {total / 60:.1f} min ({len(set(map(tuple, _grp(pkg, prof))))} chapter groups, "
                       f"voice {getattr(engine, 'last_used', engine.name)}).")
            for w in pacing_warnings(pkg["segments"], "real_seconds", prof["min_minutes"]):
                typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)
            return

        def voice_row(row: Segment) -> tuple[Segment, Path]:
            path = out / f"seg_{row.position:03d}.mp3"
            if force or not path.exists() or path.stat().st_size == 0:
                engine.synth(row.narration, path)
            return row, path

        # Synthesis waits on the network, so a few at once is much faster; results are kept in order.
        with progress.tracking(ctx.settings.project_dir(video_id), "voice", len(rows), "segments") as prog, \
                typer.progressbar(length=len(rows), label=f"Voicing {len(rows)} segments ({engine.name})") as bar, \
                ThreadPoolExecutor(VOICE_WORKERS) as pool:
            for n, (row, path) in enumerate(pool.map(voice_row, rows), 1):
                row.audio_path = str(path)
                durations[row.position] = measure(path)
                bar.update(1)
                prog.step(n, f"Voicing segment {n} of {len(rows)}")
        total = apply_real_durations(pkg, rows, durations)
        est = sum(r.est_seconds for r in rows)
        write_package(ctx, video_id, pkg)
        typer.echo(f"Narration: {total / 60:.1f} min (estimated {est / 60:.1f} min).")
        for w in pacing_warnings(pkg["segments"], "real_seconds"):
            typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)

    r = run_stage(s, video, "voiced", work, force)
    typer.echo(r.message + (f" Next: visuals {video_id}" if r.ran else ""))
