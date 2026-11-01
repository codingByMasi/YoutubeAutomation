"""`build`: stitch visuals to narration timing, add ducked music, burn captions, add intro/outro, export 1080p."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer

from studio.context import Ctx
from studio.models import Asset
from studio.providers import captions, sound
from studio.providers.whisper import cues_from_words, script_cues, to_srt, whisper_words
from studio.quality import rules
from studio.stages.base import get_video, run_stage
from studio.stages.qa import quality_report, write_report
from studio.stages.script import load_package, timeline, write_package
from studio.stages.timing import plan_segment, shot_max_for
from studio.stages.visuals import visual_paths
from studio.util import ffmpeg as ff
from studio.util.logging import get_logger

log = get_logger("build")
MUSIC_DB = -17.0  # base level; sidechain ducking pushes it a further ~8 dB down whenever the voice speaks
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}


def licence_for(path: Path) -> str:
    """Licence text from a sidecar file `<name>.licence.txt` or `<name>.txt`; 'unknown' if none."""
    sidecars = (path.with_name(path.name + ".licence.txt"), path.with_suffix(".licence.txt"), path.with_suffix(".txt"))
    for side in sidecars:
        if side.exists() and side.read_text(encoding="utf-8").strip():
            return side.read_text(encoding="utf-8").strip().splitlines()[0][:200]
    return "unknown"


def first_file(folder: Path, exts: set[str]) -> Path | None:
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in exts) if folder.exists() else []
    return files[0] if files else None


def _title_card(ctx: Ctx, prod: dict, pkg: dict, tmp: Path) -> Path | None:
    """A 3D title intro when the resolved renderer is Blender and Blender works; else None (no intro)."""
    from studio import production
    from studio.kids import build3d

    exe = build3d.choose("blender" if production.wants_blender(prod) else "2d", ctx.settings.blender_path)
    if exe is None:
        return None
    from studio.blender import title_card

    title = next((t["text"] for t in pkg.get("titles", []) if t.get("is_pick")), pkg.get("topic", ""))
    p = ff.profile()
    return title_card.make(exe, title, prod["palette"], tmp / "title3d.mp4", tmp / "title3d_frames", (p.w, p.h))


def normalize_cmd(src: Path, out: Path, with_audio: bool) -> list[str]:
    """Bring an intro/outro clip to 1920x1080/30fps/AAC 48k so it can be concatenated."""
    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if not with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-map", "0:v", "-map", "1:a"]
    return cmd + ["-vf", ff._fit(), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)]


def workers() -> int:
    """Parallel ffmpeg jobs (STUDIO_WORKERS, default 2; keep low on small hosts)."""
    try:
        return max(1, int(os.getenv("STUDIO_WORKERS", "2")))
    except ValueError:
        return 2


def photo_aspect(path: Path) -> float | None:
    """Width/height of a photo, or None if it cannot be read (the caller then crops as usual)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width / im.height
    except Exception:
        return None


def sfx_events(segs: list[dict], plans: list[list[tuple[Path, float]]]) -> list[tuple[str, float]]:
    """Sound-effect cues (kind, seconds): a whoosh into each new segment, an impact on reveals and number
    cards, and a pop whenever the next step of a chart appears."""
    events: list[tuple[str, float]] = []
    t = 0.0
    for pos, (seg, plan) in enumerate(zip(segs, plans), 1):
        big = seg.get("beat") == "reveal" or (seg.get("chart_data") or {}).get("type") == "number"
        if pos > 1:
            events.append(("hit", t) if big else ("whoosh", max(0.0, t - 0.45)))
        at, first_chart = t, True
        for src, secs in plan:
            if "charts" in src.parts:
                if not first_chart:
                    events.append(("pop", at))
                first_chart = False
            at += secs
        t = at
    return events


def render_picture(segs: list[dict], work: Path,
                   limits: dict | None = None) -> tuple[list[Path], list[list[tuple[Path, float]]]]:
    """Render every shot, cross-dissolve the shots inside each segment, and return (segment clips, plans).

    Segments are joined by a hard cut (with a whoosh); shots within a segment dissolve into each other.
    Each shot except a segment's last is rendered one dissolve longer so the segment keeps its exact length.
    """
    p = ff.profile()
    plans, jobs = [], []
    motion = 0
    for pos, seg in enumerate(segs, 1):
        backgrounds, frames = visual_paths(seg)
        duration = float(seg.get("real_seconds") or seg["est_seconds"])
        shot_max = shot_max_for(pos, limits)
        scene_clip = (seg.get("visual") or {}).get("scene_clip")
        if scene_clip and Path(scene_clip).exists():  # a 3D scene is one continuous shot, not cut every 5 s
            backgrounds, shot_max = [Path(scene_clip)], max(duration, shot_max)
        plan = plan_segment(duration, backgrounds, frames, shot_max=shot_max)
        plans.append(plan)
        for k, (src, secs) in enumerate(plan, 1):
            extra = ff.XFADE_SECONDS if (k < len(plan) and not p.draft) else 0.0
            jobs.append((src, work / f"seg_{pos:03d}_{k:02d}.mp4", secs + extra, motion))
            motion += 1

    def render(job: tuple[Path, Path, float, int]) -> None:
        src, out, secs, mo = job
        if src.suffix.lower() in IMAGE_EXT:
            charts = "charts" in src.parts
            ff.run(ff.image_cmd(src, secs, out, zoom=not charts, motion=mo,
                                aspect=None if charts else photo_aspect(src)), f"rendering {src.name}")
        else:
            ff.run(ff.clip_cmd(src, secs, out), f"rendering {src.name}")

    def join(pos: int) -> Path:
        plan = plans[pos - 1]
        files = [work / f"seg_{pos:03d}_{k:02d}.mp4" for k in range(1, len(plan) + 1)]
        out = work / f"seg_{pos:03d}.mp4"
        if len(files) == 1 or p.draft:
            ff.run(ff.concat_cmd(ff.concat_list(files, work / f"seg_{pos:03d}.txt"), out, reencode=len(files) > 1),
                   f"joining shots of segment {pos}")
        else:
            ff.run(ff.xfade_cmd(files, [s for _, s in plan], out), f"dissolving shots of segment {pos}")
        return out

    with typer.progressbar(length=len(jobs) + len(segs), label="Rendering shots") as bar, \
            ThreadPoolExecutor(workers()) as pool:
        for f in as_completed([pool.submit(render, j) for j in jobs]):
            f.result()  # re-raises the first failure
            bar.update(1)
        outs = []
        for f in [pool.submit(join, pos) for pos in range(1, len(segs) + 1)]:
            outs.append(f.result())
            bar.update(1)
    return outs, plans


def run(ctx: Ctx, video_id: int, force: bool = False) -> None:
    s = ctx.session
    video = get_video(s, video_id)

    def work() -> None:
        ff.ensure_ffmpeg()
        out = ctx.settings.project_dir(video_id)
        tmp = out / "build_tmp"
        tmp.mkdir(exist_ok=True)
        pkg = load_package(ctx, video_id)
        segs = pkg["segments"]
        assets = ctx.settings.assets_dir

        # 1. picture track
        seg_clips, plans = render_picture(segs, tmp, rules.edit_limits(ctx.settings.root))
        ff.run(ff.concat_cmd(ff.concat_list(seg_clips, tmp / "parts.txt"), tmp / "picture.mp4",
                             reencode=False), "joining segments")

        # 2. narration track
        voices = [out / "voice" / f"seg_{i:03d}.mp3" for i in range(1, len(segs) + 1)]
        ff.run(ff.audio_concat_cmd(ff.concat_list(voices, tmp / "voice.txt"), tmp / "narration.wav"),
               "joining narration")

        # 3. captions: word-timed (whisper if installed, else estimated from segment timings)
        spans = timeline(segs)
        words = whisper_words(tmp / "narration.wav")
        caption_source = "whisper" if words else "script"
        words = words or captions.words_from_script(spans, [g["narration"] for g in segs])
        cues = cues_from_words(words) if caption_source == "whisper" else script_cues(
            spans, [g["narration"] for g in segs])
        chapters, prev = [], None
        for (start, _), g in zip(spans, segs):
            if g.get("chapter") and g["chapter"] != prev and start > 0:
                chapters.append((start, g["chapter"]))
            prev = g.get("chapter")
        (out / "words.json").write_text(json.dumps({"words": words, "chapters": chapters}), encoding="utf-8")
        main_ass = captions.write_ass(tmp / "main.ass", words, captions.CaptionStyle(ff.profile().w, ff.profile().h),
                                      chapters=chapters)

        # 4. music (your own track wins; otherwise a synthesized royalty-free bed), ducked under the voice,
        #    plus sound effects on cuts, chart steps and reveals
        s.query(Asset).filter(Asset.video_id == video_id, Asset.kind.in_(["music", "intro", "outro"])).delete()
        from studio import production
        prod = production.resolve(ctx.settings, video_id)
        snd = sound.ensure_sound(assets / "cache" / "sound", prod["music_mood"])
        music = first_file(assets / "music", AUDIO_EXT) if prod["music"] != "none" else None
        if prod["music"] == "none":
            music = snd["silence"]
            s.add(Asset(video_id=video_id, kind="music", path=str(music), source="no music (channel setting)",
                        licence=sound.OWN_LICENCE))
        elif music:
            s.add(Asset(video_id=video_id, kind="music", path=str(music), source=music.name,
                        licence=licence_for(music)))
        else:
            music = snd["music"]
            s.add(Asset(video_id=video_id, kind="music", path=str(music), source="generated music bed",
                        licence=sound.OWN_LICENCE))
            typer.echo("No music in assets/music: using the generated royalty-free bed.")
        events = sfx_events(segs, plans)
        total = spans[-1][1] if spans else None
        clean = out / "clean.mp4"  # no burned captions; Shorts are cut from this
        ff.run(ff.mix_cmd(tmp / "picture.mp4", tmp / "narration.wav", clean, music, MUSIC_DB,
                          sfx={k: snd[k] for k in sound.SFX}, sfx_events=events, total=total), "mixing audio")
        main = tmp / "main.mp4"
        ff.run(["ffmpeg", "-y", "-i", str(clean), "-vf", ff._sub_filter(main_ass),
                "-c:v", "libx264", "-preset", ff.profile().preset, "-crf", str(ff.profile().crf), "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-movflags", "+faststart", str(main)], "burning captions")

        # 5. intro / outro
        pieces, intro_s = [], 0.0
        for kind in ("intro", "outro"):
            src = first_file(assets / kind, VIDEO_EXT)
            norm = tmp / f"{kind}.mp4"
            if not src and kind == "intro":
                src = _title_card(ctx, prod, pkg, tmp)
                if src:
                    ff.run(normalize_cmd(src, norm, True), "preparing intro")
                    s.add(Asset(video_id=video_id, kind=kind, path=str(src), source="generated 3D title card",
                                licence=sound.OWN_LICENCE))
                    intro_s = ff.probe_duration(norm)
                    pieces.append((kind, norm))
                continue
            if not src:
                continue
            ff.run(normalize_cmd(src, norm, ff.has_audio_stream(src)), f"preparing {kind}")
            s.add(Asset(video_id=video_id, kind=kind, path=str(src), source=src.name, licence=licence_for(src)))
            if kind == "intro":
                intro_s = ff.probe_duration(norm)
            pieces.append((kind, norm))
        final = out / "final.mp4"
        seq = [p for k, p in pieces if k == "intro"] + [main] + [p for k, p in pieces if k == "outro"]
        if len(seq) == 1:
            main.replace(final)
        else:
            ff.run(ff.concat_cmd(ff.concat_list(seq, tmp / "final.txt"), final, reencode=True), "adding intro/outro")

        # 6. upload captions match the final timeline
        (out / "captions.srt").write_text(to_srt(cues, offset=intro_s), encoding="utf-8")
        duration = ff.probe_duration(final)
        pkg["build"] = {"final": str(final), "clean": str(clean), "intro_seconds": round(intro_s, 3),
                        "duration": round(duration, 3), "music": str(music) if music else None,
                        "captions": caption_source}
        report = quality_report(pkg)
        write_report(out, report)
        for line in report["warnings"][:8]:
            typer.secho(f"quality: {line}", fg=typer.colors.YELLOW)
        write_package(ctx, video_id, pkg)
        p = ff.profile()
        typer.echo(f"Built {final} ({duration / 60:.1f} min, {p.w}x{p.h}{', DRAFT quality' if p.draft else ''}).")

    r = run_stage(s, video, "built", work, force)
    typer.echo(r.message + (f" Next: thumbnail {video_id} (optional: shorts {video_id})" if r.ran else ""))
