"""Short grow animations for bar and line chart steps (bars rise, lines draw) so charts move instead of popping in.

Each step PNG made by `charts.render_chart` gets a sibling `<name>.anim.mp4`; `build` plays it, then holds the PNG.
Other chart types are left still.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from studio.providers import brand, charts
from studio.providers.charts import DPI, fmt

FRAMES, FPS, SCALE = 20, 25, 0.75  # 0.8 s of motion at 75% size (ffmpeg scales it up)
ANIMATED = ("bar", "line", "number")


def ease(t: float) -> float:
    """Ease-out cubic: fast start, soft landing."""
    return 1 - (1 - t) ** 3


def _bar_frame(chart: dict, foot: str, k: int, p: float, path: Path) -> None:
    labels, values, unit = chart["labels"], chart["values"], chart.get("unit", "")
    fig = charts._fig()
    ax = fig.add_axes([0.06, 0.27, 0.88, 0.55])
    charts._style(ax)
    shown = [v if i < k - 1 else (v * p if i == k - 1 else 0) for i, v in enumerate(values)]
    colors = [brand.ACCENT if i == k - 1 else brand.ACCENT_2 for i in range(len(values))]
    bars = ax.bar(labels, shown, color=colors, width=0.6)
    ax.set_ylim(0, max(values) * 1.2 or 1)
    for i, b in enumerate(bars[:k]):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt(values[i] if i < k - 1 else values[i] * p, unit),
                ha="center", va="bottom", color=brand.FG, fontsize=30, fontweight="bold")
    charts._frame(fig, chart.get("title", ""), foot)
    fig.savefig(path, dpi=DPI * SCALE, facecolor=brand.BG)
    charts.plt.close(fig)


def _line_frame(chart: dict, foot: str, prev: int, k: int, p: float, path: Path) -> None:
    labels, values, unit = chart["labels"], chart["values"], chart.get("unit", "")
    n = len(values)
    reach = prev - 1 + (k - prev) * p  # how far along the x axis the line has been drawn
    whole = int(reach)
    xs = list(range(whole + 1))
    ys = [values[i] for i in xs]
    if whole + 1 < n and reach > whole:
        frac = reach - whole
        xs.append(reach)
        ys.append(values[whole] + (values[whole + 1] - values[whole]) * frac)
    fig = charts._fig()
    ax = fig.add_axes([0.06, 0.27, 0.88, 0.55])
    charts._style(ax)
    ax.plot(range(n), values, alpha=0)
    ax.plot(xs, ys, color=brand.ACCENT, linewidth=6, marker="o", markersize=12, markevery=list(range(whole + 1)))
    ax.set_xticks(range(n), labels)
    ax.set_ylim(min(0, min(values)), max(values) * 1.2 or 1)
    ax.text(xs[-1], ys[-1], " " + fmt(ys[-1], unit), color=brand.FG, fontsize=30, fontweight="bold", va="bottom")
    charts._frame(fig, chart.get("title", ""), foot)
    fig.savefig(path, dpi=DPI * SCALE, facecolor=brand.BG)
    charts.plt.close(fig)


def _number_frame(chart: dict, foot: str, p: float, path: Path) -> None:
    """Key figure counts up from 0 and swells slightly as it lands."""
    fig = charts._fig()
    size = 160 + 20 * p
    fig.text(0.5, 0.55, fmt(chart["values"][0] * p, chart.get("unit", "")), ha="center", va="center",
             color=brand.ACCENT, fontsize=size, fontweight="bold")
    fig.text(0.5, 0.32, chart["labels"][0], ha="center", va="center", color=brand.FG, fontsize=48, alpha=min(1, p * 2))
    charts._frame(fig, chart.get("title", ""), foot)
    fig.savefig(path, dpi=DPI * SCALE, facecolor=brand.BG)
    charts.plt.close(fig)


def _encode(frames: Path, out: Path) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames / "a_%03d.png"), "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", str(out)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def animate(chart: dict, steps: list[Path], foot: str, work: Path) -> dict[str, str]:
    """Write `<step>.anim.mp4` next to every step PNG of a bar/line chart; returns {png: mp4} (empty if skipped).

    Never raises for animation trouble: a chart without its animation is simply shown still.
    """
    if chart.get("type") not in ANIMATED or not steps:
        return {}
    done: dict[str, str] = {}
    n = len(chart["values"])
    prev = 0 if chart["type"] == "bar" else 1
    for png in steps:
        try:
            k = int(png.stem.rsplit("_step", 1)[1])
            fdir = work / f"{png.stem}_anim"
            fdir.mkdir(parents=True, exist_ok=True)
            for i in range(FRAMES):
                p = ease((i + 1) / FRAMES)
                out = fdir / f"a_{i + 1:03d}.png"
                if chart["type"] == "number":
                    _number_frame(chart, foot, p, out)
                elif chart["type"] == "bar":
                    _bar_frame(chart, foot, k, p, out)
                else:
                    _line_frame(chart, foot, max(prev, 1), min(k, n), p, out)
            mp4 = png.with_suffix(".anim.mp4")
            if _encode(fdir, mp4):
                done[str(png)] = str(mp4)
            shutil.rmtree(fdir, ignore_errors=True)
        except Exception:  # noqa: BLE001 - animation is a bonus; the still chart stays
            continue
        prev = k
    return done
