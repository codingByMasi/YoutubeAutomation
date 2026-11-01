"""2D motion-graphic versions of the scene kinds (PNG step frames, 1920x1080), drawn with matplotlib.

Each scene is a few frames in which the next milestone, place or object appears; `build` shows them in order,
the same way chart steps are revealed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib.patches import Circle, Ellipse, Rectangle

from studio.providers import brand
from studio.providers.charts import MAX_STEPS, _fig, _frame, _save


def _steps(n: int) -> list[int]:
    """Which item counts get a frame: every step, or the last MAX_STEPS ones when there are many."""
    return list(range(1, n + 1))[-MAX_STEPS:]


def _canvas(title: str, foot: str):
    fig = _fig()
    _frame(fig, title, foot)
    ax = fig.add_axes([0.04, 0.12, 0.92, 0.7])
    ax.set_facecolor(brand.BG)
    ax.axis("off")
    return fig, ax


def timeline(scene: dict, foot: str, out: Path, stem: str) -> list[Path]:
    """A horizontal line; milestones appear left to right, labels alternating above and below."""
    items, paths = scene["items"], []
    n = len(items)
    for k in _steps(n):
        fig, ax = _canvas(scene.get("title", ""), foot)
        ax.set_xlim(-0.5, n - 0.5)
        ax.set_ylim(-3, 3)
        ax.plot([-0.5, n - 0.5], [0, 0], color=brand.MUTED, lw=4, solid_capstyle="round")
        for i, it in enumerate(items[:k]):
            up = 1 if i % 2 == 0 else -1
            current = i == k - 1
            ax.plot([i, i], [0, 0.9 * up], color=brand.MUTED, lw=2)
            ax.add_patch(Circle((i, 0), 0.09, color=brand.ACCENT if current else brand.SERIES[1], zorder=3))
            ax.text(i, 1.15 * up, it["label"], color=brand.ACCENT, fontsize=34, fontweight="bold", ha="center",
                    va="bottom" if up > 0 else "top")
            ax.text(i, 1.85 * up if up > 0 else -1.85, textwrap.fill(it.get("text", ""), 22), color=brand.FG,
                    fontsize=22, ha="center", va="bottom" if up > 0 else "top")
        paths.append(_save(fig, out / f"{stem}_{k:02d}.png"))
    return paths


def route_map(scene: dict, foot: str, out: Path, stem: str) -> list[Path]:
    """A schematic map: places appear one after another and a route line draws between them."""
    items, paths = scene["items"], []
    for k in _steps(len(items)):
        fig, ax = _canvas(scene.get("title", ""), foot)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.add_patch(Rectangle((0, 0), 1, 1, color=brand.MUTED, alpha=0.12, zorder=0))
        for gx in (0.25, 0.5, 0.75):
            ax.axvline(gx, color=brand.MUTED, alpha=0.15, lw=1)
            ax.axhline(gx, color=brand.MUTED, alpha=0.15, lw=1)
        shown = items[:k]
        xs = [float(i["x"]) for i in shown]
        ys = [1 - float(i["y"]) for i in shown]
        ax.plot(xs, ys, color=brand.ACCENT, lw=5, solid_capstyle="round", zorder=2)
        for i, it in enumerate(shown):
            ax.add_patch(Circle((xs[i], ys[i]), 0.012, color=brand.ACCENT if i == k - 1 else brand.SERIES[1], zorder=3))
            ax.text(xs[i], ys[i] + 0.04, it["label"], color=brand.FG, fontsize=26, fontweight="bold", ha="center",
                    va="bottom", zorder=4)
        paths.append(_save(fig, out / f"{stem}_{k:02d}.png"))
    return paths


def _artifact_shapes(ax, shape: str) -> None:
    a, m = brand.ACCENT, brand.MUTED
    if shape == "column":
        ax.add_patch(Rectangle((-0.7, -2.0), 1.4, 0.3, color=m))
        ax.add_patch(Rectangle((-0.45, -1.7), 0.9, 3.0, color=a))
        ax.add_patch(Rectangle((-0.7, 1.3), 1.4, 0.3, color=m))
    elif shape == "vase":
        ax.add_patch(Ellipse((0, -0.4), 2.2, 2.6, color=a))
        ax.add_patch(Rectangle((-0.4, 0.7), 0.8, 1.0, color=a))
        ax.add_patch(Rectangle((-0.65, 1.6), 1.3, 0.2, color=m))
    elif shape == "box":
        ax.add_patch(Rectangle((-1.2, -1.0), 2.4, 2.0, color=a))
        ax.add_patch(Rectangle((-1.2, 0.5), 2.4, 0.15, color=m))
    else:  # coin
        ax.add_patch(Circle((0, 0), 1.5, color=a))
        ax.add_patch(Circle((0, 0), 1.2, color=brand.BG))
        ax.add_patch(Circle((0, 0), 1.0, color=a))


def artifact(scene: dict, foot: str, out: Path, stem: str) -> list[Path]:
    """One flat object on a pedestal line with its name; a single frame."""
    it = scene["items"][0]
    fig, ax = _canvas(scene.get("title", ""), foot)
    ax.set_xlim(-4, 4)
    ax.set_ylim(-3, 3)
    ax.set_aspect("equal")
    _artifact_shapes(ax, it.get("shape", "coin"))
    ax.plot([-2.5, 2.5], [-2.1, -2.1], color=brand.MUTED, lw=5)
    ax.text(0, -2.6, it["label"], color=brand.FG, fontsize=34, ha="center", va="top")
    return [_save(fig, out / f"{stem}_01.png")]


DRAWERS = {"timeline": timeline, "map": route_map, "artifact": artifact}


def render(scene: dict, foot: str, out: Path, stem: str) -> list[Path]:
    """Frames for a scene kind, or [] for chart3d (the segment's normal 2D chart is its equivalent)."""
    out.mkdir(parents=True, exist_ok=True)
    draw = DRAWERS.get(scene["kind"])
    return draw(scene, foot, out, stem) if draw else []
