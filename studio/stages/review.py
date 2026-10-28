"""`review`: pre-publish checklist plus the typed 'yes' gate. Writes review.json."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import typer

from studio.context import Ctx
from studio.errors import GateError, StudioError
from studio.models import Asset
from studio.stages.base import get_video, run_stage
from studio.stages.script import banned_in, load_package, timeline, validate_package, validate_title
from studio.stages.thumbnail import validate_thumb

DISCLAIMER = "Educational content only, not financial advice. Figures are from the sources listed; " \
             "estimates are labelled."
CATEGORY_EDUCATION = "27"
TAGS_MAX_CHARS = 500
DESC_MAX_CHARS = 5000
CHAPTER_MIN_SECONDS = 10


def require_yes(confirm, prompt: str, action: str) -> None:
    """Raise GateError unless the owner types exactly 'yes'."""
    answer = confirm(prompt)
    if (answer or "").strip().lower() != "yes":
        raise GateError(f"Not approved: {action} cancelled.", f"You typed {answer!r}, not 'yes'.",
                        "Re-run the command and type yes when you are happy.")


def mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapters(segs: list[dict], intro_seconds: float = 0.0) -> list[tuple[float, str]]:
    """YouTube chapters: first at 0:00, consecutive same-name segments merged, each at least 10 s."""
    out: list[list] = []
    for (start, _), seg in zip(timeline(segs), segs):
        name = (seg.get("chapter") or "").strip() or "Part"
        if out and out[-1][1] == name:
            continue
        out.append([start + intro_seconds, name])
    if not out:
        return []
    out[0][0] = 0.0
    total = timeline(segs)[-1][1] + intro_seconds
    merged: list[list] = []
    for i, (start, name) in enumerate(out):
        end = out[i + 1][0] if i + 1 < len(out) else total
        if merged and (end - start < CHAPTER_MIN_SECONDS or start - merged[-1][0] < CHAPTER_MIN_SECONDS):
            continue  # too short: fold into the previous chapter
        merged.append([start, name])
    return [(s, n) for s, n in merged]


def build_description(pkg: dict, chaps: list[tuple[float, str]], licences: list[dict]) -> str:
    """Description template: summary, chapters, sources, disclaimer, credits."""
    parts = [pkg.get("description_summary", "").strip()]
    if len(chaps) >= 3:
        parts.append("Chapters\n" + "\n".join(f"{mmss(t)} {n}" for t, n in chaps))
    if pkg.get("sources"):
        parts.append("Sources\n" + "\n".join(f"- {s.get('title', '')}: {s['url_or_note']}" for s in pkg["sources"]))
    parts.append(DISCLAIMER)
    if any("Pexels" in lic["licence"] for lic in licences):
        parts.append("Stock footage from Pexels (https://www.pexels.com).")
    return "\n\n".join(p for p in parts if p)


def fit_tags(tags: list[str]) -> list[str]:
    out, total = [], 0
    for t in tags:
        t = t.replace("<", "").replace(">", "").strip()
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if t and total + cost <= TAGS_MAX_CHARS:
            out.append(t)
            total += cost
    return out


def file_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def collect(ctx: Ctx, video_id: int, thumb: int, title: str | None) -> tuple[dict, list[str]]:
    """Everything the checklist shows, plus blocking problems."""
    pkg = load_package(ctx, video_id)
    out = ctx.settings.project_dir(video_id)
    problems: list[str] = []
    pick = title or next((t["text"] for t in pkg["titles"] if t.get("is_pick")), "")
    problems += validate_title(pick)
    problems += [p for p in validate_package(pkg) if "chart" in p or "source" in p or "banned" in p]
    assets = ctx.session.query(Asset).filter_by(video_id=video_id).all()
    licences = [{"kind": a.kind, "path": a.path, "licence": a.licence, "source": a.source,
                 "attribution_url": a.attribution_url} for a in assets]
    for a in assets:
        if not a.licence or a.licence.strip().lower() == "unknown":
            problems.append(f"unknown licence for {a.kind} {Path(a.path).name}: add a licence note "
                            f"({Path(a.path).name}.licence.txt) or remove the file, then rebuild")
    final, srt = out / "final.mp4", out / "captions.srt"
    thumb_path = out / "thumbs" / f"thumb_{thumb}.jpg"
    for f in (final, srt, thumb_path):
        if not f.exists():
            problems.append(f"missing file {f}")
    if thumb_path.exists():
        problems += validate_thumb(thumb_path)
    chaps = chapters(pkg["segments"], float(pkg.get("build", {}).get("intro_seconds", 0)))
    description = build_description(pkg, chaps, licences)
    if len(description) > DESC_MAX_CHARS:
        problems.append(f"description is {len(description)} chars (max {DESC_MAX_CHARS})")
    for p in banned_in(description):
        problems.append(f"description uses banned phrase {p!r}")
    data = {
        "video_id": video_id, "title": pick, "description": description, "tags": fit_tags(pkg.get("tags", [])),
        "category_id": CATEGORY_EDUCATION, "chapters": [[round(t, 1), n] for t, n in chaps],
        "thumbnail": str(thumb_path), "files": {"video": str(final), "captions": str(srt)},
        "synthetic_media": bool(pkg.get("synthetic_media")), "licences": licences,
        "duration": pkg.get("build", {}).get("duration"),
    }
    return data, problems


def print_checklist(d: dict, problems: list[str]) -> None:
    e = typer.echo
    e(f"\n=== Review: video {d['video_id']} ===")
    e(f"Title ({len(d['title'])} chars): {d['title']}")
    e(f"Duration: {(d['duration'] or 0) / 60:.1f} min")
    e(f"Tags: {', '.join(d['tags'])}")
    e(f"Chapters: {len(d['chapters'])}" + ("" if len(d["chapters"]) >= 3 else " (YouTube needs 3+; none shown)"))
    for t, n in d["chapters"]:
        e(f"   {mmss(t)} {n}")
    e(f"Thumbnail: {d['thumbnail']}")
    e(f"Video: {d['files']['video']}\nCaptions: {d['files']['captions']}")
    e(f"Altered/synthetic content disclosure: {'YES (will be declared)' if d['synthetic_media'] else 'no'}")
    e("Licences:")
    seen = set()
    for lic in d["licences"]:
        key = (lic["kind"], lic["licence"])
        if key not in seen:
            seen.add(key)
            count = sum(1 for x in d["licences"] if (x["kind"], x["licence"]) == key)
            e(f"   {count} x {lic['kind']}: {lic['licence']}")
    e("\n--- Description ---\n" + d["description"] + "\n-------------------")
    if problems:
        typer.secho("\nBLOCKING PROBLEMS:", fg=typer.colors.RED)
        for p in problems:
            typer.secho(f"  - {p}", fg=typer.colors.RED)


def run(ctx: Ctx, video_id: int, thumb: int = 1, title: str | None = None, force: bool = False) -> None:
    video = get_video(ctx.session, video_id)

    def work() -> None:
        data, problems = collect(ctx, video_id, thumb, title)
        print_checklist(data, problems)
        if problems:
            raise StudioError(f"Review failed for video {video_id}: {len(problems)} problem(s) listed above.",
                              "Publishing is blocked until every problem is fixed.",
                              "Fix them, re-run the stage that produces the file, then `review` again.")
        require_yes(ctx.confirm, f"\nWatch {data['files']['video']} fully first.\n"
                                 f"Type yes to approve video {video_id} for publishing: ", "review")
        data["approved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data["video_sha256"] = file_fingerprint(Path(data["files"]["video"]))
        (ctx.settings.project_dir(video_id) / "review.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    r = run_stage(ctx.session, video, "reviewed", work, force)
    typer.echo(r.message + (f" Next: publish {video_id} --at \"YYYY-MM-DD HH:MM\"" if r.ran else ""))
