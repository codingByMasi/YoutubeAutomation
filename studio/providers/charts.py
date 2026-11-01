"""Charts, flow diagrams, number cards and text cards rendered from `chart_data` (1920x1080 PNG).

Each chart renders as a few step frames (bars or flow steps appear one by one); `build` shows the
frames in sequence so the figure is revealed, not dumped on screen.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image, ImageDraw, ImageFont

from studio.errors import StudioError
from studio.providers import brand

W, H, DPI = 1920, 1080, 100
MAX_STEPS = 6


def fmt(value: float, unit: str) -> str:
    """Format a value with its unit: $1.2, 35%, 4.1B."""
    v = f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"
    if unit in {"$", "₹", "€", "£"}:
        if isinstance(value, float) and not value.is_integer():
            v = f"{value:,.2f}"
        return f"{unit}{v}"
    if unit in {"%", "x"}:
        return f"{v}{unit}"
    m = re.match(r"^(?P<scale>thousand|million|billion|trillion)?\s*(?P<cur>US\$|USD|\$|US dollars?|dollars?)$",
                 unit.strip(), re.I)
    if m and m["cur"]:
        return f"${v} {m['scale'].lower()}".strip() if m["scale"] else f"${v}"
    return f"{v} {unit}".strip()


def _needs_source(chart: dict) -> bool:
    from studio.stages.script import chart_needs_source
    return chart_needs_source(chart)


def source_line(chart: dict, sources: list[dict]) -> str:
    """Footnote naming every cited source; raises if the chart has none."""
    by_id = {s["id"]: s for s in sources}
    names = [by_id[i].get("title") or by_id[i]["url_or_note"] for i in chart.get("source_ids", []) if i in by_id]
    if not names and chart and not _needs_source(chart):
        return "Illustration, not real data" if chart.get("type") != "flow" else "Concept diagram"
    if not names:
        raise StudioError(f"Chart {chart.get('title', '')!r} has no source.", "Every figure needs a source.",
                          "Add source_ids to the chart in script.json and re-run `visuals --force`.")
    tag = "Estimate. " if chart.get("is_estimate") else ""
    return f"{tag}Source: {'; '.join(names)}"


def _fig():
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=brand.BG)
    return fig


def _frame(fig, title: str, footnote: str) -> None:
    fig.text(0.06, 0.9, title, color=brand.FG, fontsize=44, fontweight="bold", va="center")
    fig.text(0.06, 0.05, textwrap.shorten(footnote, 150), color=brand.MUTED, fontsize=18, va="center")


def _style(ax) -> None:
    ax.set_facecolor(brand.BG)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(brand.MUTED)
    ax.tick_params(colors=brand.FG, labelsize=24, length=0)
    ax.set_yticks([])


def _save(fig, path: Path) -> Path:
    fig.savefig(path, dpi=DPI, facecolor=brand.BG)
    plt.close(fig)
    return path


def _bar(chart, foot, out: Path, stem: str) -> list[Path]:
    labels, values, unit = chart["labels"], chart["values"], chart.get("unit", "")
    paths = []
    steps = list(range(1, len(labels) + 1))[-MAX_STEPS:] if len(labels) > MAX_STEPS else range(1, len(labels) + 1)
    for k in steps:
        fig = _fig()
        ax = fig.add_axes([0.06, 0.27, 0.88, 0.55])
        _style(ax)
        shown = [v if i < k else 0 for i, v in enumerate(values)]
        colors = [brand.ACCENT if i == k - 1 else brand.ACCENT_2 for i in range(len(values))]
        bars = ax.bar(labels, shown, color=colors, width=0.6)
        ax.set_ylim(0, max(values) * 1.2 or 1)
        for i, b in enumerate(bars[:k]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt(values[i], unit), ha="center", va="bottom",
                    color=brand.FG, fontsize=30, fontweight="bold")
        _frame(fig, chart.get("title", ""), foot)
        paths.append(_save(fig, out / f"{stem}_step{k}.png"))
    return paths


def _line(chart, foot, out: Path, stem: str) -> list[Path]:
    labels, values, unit = chart["labels"], chart["values"], chart.get("unit", "")
    n = len(values)
    cut = sorted({max(2, round(n * f)) for f in (0.34, 0.67, 1.0)}) if n > 2 else [n]
    paths = []
    for k in cut:
        fig = _fig()
        ax = fig.add_axes([0.06, 0.27, 0.88, 0.55])
        _style(ax)
        ax.plot(range(n), values, alpha=0)  # fixes axes
        ax.plot(range(k), values[:k], color=brand.ACCENT, linewidth=6, marker="o", markersize=12)
        ax.set_xticks(range(n), labels)
        ax.set_ylim(min(0, min(values)), max(values) * 1.2 or 1)
        ax.text(k - 1, values[k - 1], " " + fmt(values[k - 1], unit), color=brand.FG, fontsize=30,
                fontweight="bold", va="bottom")
        _frame(fig, chart.get("title", ""), foot)
        paths.append(_save(fig, out / f"{stem}_step{k}.png"))
    return paths


def _pie(chart, foot, out: Path, stem: str) -> list[Path]:
    fig = _fig()
    ax = fig.add_axes([0.25, 0.22, 0.5, 0.62])
    unit = chart.get("unit", "")
    ax.pie(chart["values"], labels=[f"{lb}\n{fmt(v, unit)}" for lb, v in zip(chart["labels"], chart["values"])],
           colors=brand.SERIES[: len(chart["values"])], startangle=90, counterclock=False,
           wedgeprops={"width": 0.42, "edgecolor": brand.BG, "linewidth": 4},
           textprops={"color": brand.FG, "fontsize": 24, "fontweight": "bold"})
    _frame(fig, chart.get("title", ""), foot)
    return [_save(fig, out / f"{stem}_step1.png")]


def _flow(chart, foot, out: Path, stem: str) -> list[Path]:
    labels = chart["labels"][:MAX_STEPS]
    values, unit = chart.get("values") or [], chart.get("unit", "")
    n = len(labels)
    box_w, gap = 0.8 / n * 0.75, 0.8 / n
    paths = []
    for k in range(1, n + 1):
        fig = _fig()
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        for i in range(k):
            x = 0.1 + i * gap
            ax.add_patch(FancyBboxPatch((x, 0.4), box_w, 0.2, boxstyle="round,pad=0.01,rounding_size=0.02",
                                        fc=brand.ACCENT if i == k - 1 else "#1E293B", ec=brand.ACCENT_2, lw=3))
            text = "\n".join(textwrap.wrap(labels[i], 14))
            if i < len(values):
                text += f"\n{fmt(values[i], unit)}"
            ax.text(x + box_w / 2, 0.5, text, ha="center", va="center", fontsize=26, fontweight="bold",
                    color=brand.BG if i == k - 1 else brand.FG)
            if i:
                ax.add_patch(FancyArrowPatch((x - gap + box_w + 0.005, 0.5), (x - 0.005, 0.5),
                                             arrowstyle="-|>", mutation_scale=40, color=brand.FG, lw=3))
        _frame(fig, chart.get("title", ""), foot)
        paths.append(_save(fig, out / f"{stem}_step{k}.png"))
    return paths


def _number(chart, foot, out: Path, stem: str) -> list[Path]:
    fig = _fig()
    text = fmt(chart["values"][0], chart.get("unit", ""))
    size = max(60, min(180, int(1500 / max(len(text), 1) * 1.5)))  # keep the figure inside the frame
    fig.text(0.5, 0.55, text, ha="center", va="center", color=brand.ACCENT, fontsize=size, fontweight="bold")
    fig.text(0.5, 0.32, chart["labels"][0], ha="center", va="center", color=brand.FG, fontsize=48)
    _frame(fig, chart.get("title", ""), foot)
    return [_save(fig, out / f"{stem}_step1.png")]


RENDERERS = {"bar": _bar, "line": _line, "pie": _pie, "flow": _flow, "number": _number}


def render_chart(chart: dict, sources: list[dict], out_dir: Path, stem: str) -> list[Path]:
    """Render step frames for a chart. Raises StudioError if it has no source.

    Sources are validated here but not drawn on the frame; they go in the video description.
    """
    source_line(chart, sources)
    foot = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return RENDERERS[chart["type"]](chart, foot, out_dir, stem)
    except KeyError as exc:
        raise StudioError(f"Unknown chart type {chart.get('type')!r}.", "",
                          f"Use one of {sorted(RENDERERS)} in script.json.") from exc


def text_card(text: str, sub: str, out: Path, assets_dir: Path | None = None) -> Path:
    """Fallback visual when no stock clip is found: a clean title card."""
    img = Image.new("RGB", (W, H), brand.BG)
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(brand.font_path(assets_dir), 96)
    small = ImageFont.truetype(brand.font_path(assets_dir, bold=False), 40)
    lines = textwrap.wrap(text, 26)[:3]
    y = H // 2 - len(lines) * 60
    d.rectangle([140, y - 40, 152, y + len(lines) * 120 - 40], fill=brand.ACCENT)
    for line in lines:
        d.text((190, y), line, font=big, fill=brand.FG, anchor="lm")
        y += 120
    if sub:
        d.text((190, y + 20), textwrap.shorten(sub, 70), font=small, fill=brand.MUTED, anchor="lm")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
