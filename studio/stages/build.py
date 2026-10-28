"""`build`: stitch visuals to narration timing, add ducked music, burn captions, add intro/outro, export 1080p."""

from __future__ import annotations

from pathlib import Path

import typer

from studio.context import Ctx
from studio.models import Asset
from studio.providers.whisper import script_cues, to_srt, whisper_cues
from studio.stages.base import get_video, run_stage
from studio.stages.script import load_package, timeline, write_package
from studio.stages.timing import plan_segment
from studio.stages.visuals import visual_paths
from studio.util import ffmpeg as ff
from studio.util.logging import get_logger

log = get_logger("build")
MUSIC_DB = -20.0  # style guide: music at least 15 dB under the voice
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}


def licence_for(path: Path) -> str:
    """Licence text from a sidecar file `<name>.licence.txt` or `<name>.txt`; 'unknown' if none."""
    for side in (path.with_name(path.name + ".licence.txt"), path.with_suffix(".licence.txt"), path.with_suffix(".txt")):
        if side.exists() and side.read_text(encoding="utf-8").strip():
            return side.read_text(encoding="utf-8").strip().splitlines()[0][:200]
    return "unknown"


def first_file(folder: Path, exts: set[str]) -> Path | None:
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in exts) if folder.exists() else []
    return files[0] if files else None


def normalize_cmd(src: Path, out: Path, with_audio: bool) -> list[str]:
    """Bring an intro/outro clip to 1920x1080/30fps/AAC 48k so it can be concatenated."""
    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if not with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-map", "0:v", "-map", "1:a"]
    return cmd + ["-vf", ff._fit(), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)]


def render_parts(segs: list[dict], work: Path) -> list[Path]:
    """Render every planned part of every segment to a silent 1080p clip."""
    parts: list[Path] = []
    plans = []
    for pos, seg in enumerate(segs, 1):
        backgrounds, frames = visual_paths(seg)
        plans.append((pos, plan_segment(float(seg.get("real_seconds") or seg["est_seconds"]), backgrounds, frames)))
    total = sum(len(p) for _, p in plans)
    with typer.progressbar(length=total, label="Rendering shots") as bar:
        for pos, plan in plans:
            for k, (src, secs) in enumerate(plan, 1):
                out = work / f"seg_{pos:03d}_{k:02d}.mp4"
                if src.suffix.lower() in IMAGE_EXT:
                    ff.run(ff.image_cmd(src, secs, out, zoom="charts" not in src.parts), f"rendering {src.name}")
                else:
                    ff.run(ff.clip_cmd(src, secs, out), f"rendering {src.name}")
                parts.append(out)
                bar.update(1)
    return parts


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
        parts = render_parts(segs, tmp)
        ff.run(ff.concat_cmd(ff.concat_list(parts, tmp / "parts.txt"), tmp / "picture.mp4"), "joining shots")

        # 2. narration track
        voices = [Path(ctx.settings.project_dir(video_id) / "voice" / f"seg_{i:03d}.mp3") for i in range(1, len(segs) + 1)]
        ff.run(ff.audio_concat_cmd(ff.concat_list(voices, tmp / "voice.txt"), tmp / "narration.wav"),
               "joining narration")

        # 3. captions (whisper if installed, else script-timed)
        spans = timeline(segs)
        cues = whisper_cues(tmp / "narration.wav")
        caption_source = "whisper" if cues else "script"
        cues = cues or script_cues(spans, [g["narration"] for g in segs])
        main_srt = tmp / "main.srt"
        main_srt.write_text(to_srt(cues), encoding="utf-8")

        # 4. music, mixed under the voice
        s.query(Asset).filter(Asset.video_id == video_id, Asset.kind.in_(["music", "intro", "outro"])).delete()
        music = first_file(assets / "music", AUDIO_EXT)
        if music:
            s.add(Asset(video_id=video_id, kind="music", path=str(music), source=music.name,
                        licence=licence_for(music)))
        else:
            typer.secho("No music in assets/music; building with narration only.", fg=typer.colors.YELLOW)
        clean = out / "clean.mp4"  # no burned captions; Shorts are cut from this
        ff.run(ff.mix_cmd(tmp / "picture.mp4", tmp / "narration.wav", clean, music, MUSIC_DB), "mixing audio")
        main = tmp / "main.mp4"
        ff.run(["ffmpeg", "-y", "-i", str(clean), "-vf",
                f"subtitles='{ff._escape_sub(main_srt)}':force_style='{ff.SUB_STYLE}'",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
                "-movflags", "+faststart", str(main)], "burning captions")

        # 5. intro / outro
        pieces, intro_s = [], 0.0
        for kind in ("intro", "outro"):
            src = first_file(assets / kind, VIDEO_EXT)
            if not src:
                continue
            norm = tmp / f"{kind}.mp4"
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
        write_package(ctx, video_id, pkg)
        typer.echo(f"Built {final} ({duration / 60:.1f} min, 1920x1080).")

    r = run_stage(s, video, "built", work, force)
    typer.echo(r.message + (f" Next: thumbnail {video_id} (optional: shorts {video_id})" if r.ran else ""))
