"""`thumbnail`: 3 variants (different text and layout), 1280x720 JPEG under 2 MB each."""

from __future__ import annotations

import io
import subprocess
import textwrap
from pathlib import Path

import typer
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from studio.context import Ctx
from studio.providers import brand
from studio.stages.base import get_video, run_stage
from studio.stages.script import load_package, timeline, write_package
from studio.util.ffmpeg import ensure_ffmpeg

TW, TH = 1280, 720
MAX_BYTES = 2 * 1024 * 1024


def save_under_limit(img: Image.Image, out: Path, max_bytes: int = MAX_BYTES) -> Path:
    """Save as JPEG, lowering quality until the file is under max_bytes."""
    img = img.convert("RGB")
    if img.size != (TW, TH):
        img = img.resize((TW, TH), Image.LANCZOS)
    for q in (92, 85, 78, 70, 60, 50, 40):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() < max_bytes:
            out.write_bytes(buf.getvalue())
            return out
    raise ValueError(f"Could not get {out.name} under {max_bytes} bytes")


def validate_thumb(path: Path) -> list[str]:
    """Problems with a thumbnail file: wrong size or too large."""
    problems = []
    with Image.open(path) as im:
        if im.size != (TW, TH):
            problems.append(f"{path.name} is {im.size[0]}x{im.size[1]}, must be {TW}x{TH}")
    if path.stat().st_size >= MAX_BYTES:
        problems.append(f"{path.name} is {path.stat().st_size / 1e6:.1f} MB, must be under 2 MB")
    return problems


def _font(assets: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(brand.font_path(assets), size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, assets: Path, max_w: int, max_lines: int, start: int):
    """Largest font size where the wrapped text fits max_w in max_lines."""
    for size in range(start, 40, -6):
        f = _font(assets, size)
        width_chars = max(4, int(max_w / (size * 0.55)))
        lines = textwrap.wrap(text.upper(), width_chars)
        if len(lines) <= max_lines and all(draw.textlength(ln, font=f) <= max_w for ln in lines):
            return f, lines
    f = _font(assets, 40)
    return f, textwrap.wrap(text.upper(), 20)[:max_lines]


def _outlined(draw, xy, text, font, fill, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=max(2, font.size // 18),
              stroke_fill="#000000")


def grab_frame(video: Path, at: float, out: Path) -> Path | None:
    """One frame from the built video, or None if ffmpeg/video is unavailable."""
    try:
        ensure_ffmpeg()
        subprocess.run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(out)],
                       capture_output=True, check=True)
        return out if out.exists() else None
    except Exception:  # noqa: BLE001 - thumbnails still work without a frame
        return None


def _background(frame: Path | None) -> Image.Image:
    if frame and frame.exists():
        img = Image.open(frame).convert("RGB")
        r = max(TW / img.width, TH / img.height)
        img = img.resize((int(img.width * r) + 1, int(img.height * r) + 1), Image.LANCZOS)
        left, top = (img.width - TW) // 2, (img.height - TH) // 2
        return img.crop((left, top, left + TW, top + TH))
    return Image.new("RGB", (TW, TH), brand.BG)


def _overlay(img: Image.Image, assets: Path) -> Image.Image:
    """Optional brand overlay: assets/thumb_templates/overlay.png (1280x720 with transparency)."""
    ov = assets / "thumb_templates" / "overlay.png"
    if ov.exists():
        layer = Image.open(ov).convert("RGBA").resize((TW, TH))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return img


def layout_split(text: str, frame: Path | None, assets: Path) -> Image.Image:
    """Text block on the left, framed picture on the right."""
    img = Image.new("RGB", (TW, TH), brand.BG)
    pic = _background(frame).resize((680, 383), Image.LANCZOS)
    img.paste(Image.new("RGB", (692, 395), brand.ACCENT), (TW - 692 - 36, (TH - 395) // 2))
    img.paste(pic, (TW - 680 - 42, (TH - 383) // 2))
    d = ImageDraw.Draw(img)
    f, lines = _fit_text(d, text, assets, 470, 3, 120)
    y = TH // 2 - len(lines) * f.size * 0.6
    for ln in lines:
        _outlined(d, (48, y), ln, f, brand.FG)
        y += f.size * 1.15
    return img


def layout_fullbleed(text: str, frame: Path | None, assets: Path) -> Image.Image:
    """Full-frame picture, darkened, with big text and an accent bar along the bottom."""
    img = ImageEnhance.Brightness(_background(frame).filter(ImageFilter.GaussianBlur(1))).enhance(0.55)
    d = ImageDraw.Draw(img)
    f, lines = _fit_text(d, text, assets, TW - 120, 2, 150)
    y = TH - 70 - len(lines) * f.size * 1.1
    for i, ln in enumerate(lines):
        _outlined(d, (60, y), ln, f, brand.ACCENT if i == len(lines) - 1 else brand.FG)
        y += f.size * 1.1
    d.rectangle([60, TH - 50, 420, TH - 36], fill=brand.ACCENT)
    return img


def layout_number(text: str, number: str | None, assets: Path) -> Image.Image:
    """Solid brand background with one huge number (if the video has one) above the text."""
    img = Image.new("RGB", (TW, TH), brand.BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 24, TH], fill=brand.ACCENT)
    if number:
        f_num = _font(assets, 260)
        while d.textlength(number, font=f_num) > TW - 160 and f_num.size > 120:
            f_num = _font(assets, f_num.size - 20)
        _outlined(d, (TW // 2, TH * 0.4), number, f_num, brand.ACCENT, anchor="mm")
    f, lines = _fit_text(d, text, assets, TW - 160, 2 if number else 3, 110 if number else 140)
    y = TH * (0.72 if number else 0.5) - (len(lines) - 1) * f.size * 0.55
    for ln in lines:
        _outlined(d, (TW // 2, y), ln, f, brand.FG, anchor="mm")
        y += f.size * 1.1
    return img


def headline_number(pkg: dict) -> str | None:
    from studio.providers.charts import fmt

    for seg in pkg["segments"]:
        c = seg.get("chart_data") or {}
        if c.get("type") == "number":
            return fmt(c["values"][0], c.get("unit", ""))
    return None


def run(ctx: Ctx, video_id: int, force: bool = False) -> list[Path]:
    s = ctx.session
    video = get_video(s, video_id)
    made: list[Path] = []

    def work() -> None:
        out = ctx.settings.project_dir(video_id) / "thumbs"
        out.mkdir(exist_ok=True)
        pkg = load_package(ctx, video_id)
        assets = ctx.settings.assets_dir
        texts = (pkg.get("thumbnail_texts") or ["", "", ""])[:3]
        spans = timeline(pkg["segments"])
        # a frame from the first stock-footage segment, else from the middle of the video
        idx = next((i for i, g in enumerate(pkg["segments"])
                    if (g.get("visual") or {}).get("kind") in ("clip", "image")), None)
        at = (spans[idx][0] + 1.0) if idx is not None else spans[-1][1] / 2
        clean = Path(pkg.get("build", {}).get("clean") or ctx.settings.project_dir(video_id) / "clean.mp4")
        frame = grab_frame(clean, at, out / "frame.png") if clean.exists() else None
        images = [layout_split(texts[0], frame, assets), layout_fullbleed(texts[1], frame, assets),
                  layout_number(texts[2], headline_number(pkg), assets)]
        for i, img in enumerate(images, 1):
            p = save_under_limit(_overlay(img, assets), out / f"thumb_{i}.jpg")
            problems = validate_thumb(p)
            if problems:
                raise ValueError("; ".join(problems))
            made.append(p)
        pkg["thumbnails"] = [str(p) for p in made]
        write_package(ctx, video_id, pkg)
        typer.echo(f"Thumbnails: {', '.join(p.name for p in made)} in {out}")

    r = run_stage(s, video, "thumbnailed", work, force)
    typer.echo(r.message + (f" Next: watch final.mp4, then review {video_id}" if r.ran else ""))
    return made
