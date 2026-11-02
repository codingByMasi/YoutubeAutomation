"""Time budget for 3D scenes: measures Blender's speed, shortens or drops 3D scenes that would take too long."""

from __future__ import annotations

import os
import time
from pathlib import Path

from studio.blender.provider import SceneTooSlow
from studio.util import progress
from studio.util.progress import fmt_duration

MIN_SECONDS = 6.0  # shorter than this is not worth a 3D clip; draw the scene in 2D instead


def _env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


class SceneBudget:
    """Limits for one `visuals` run.

    SCENE_3D_TIMEOUT: most seconds one scene may take (default 600). A scene that would take longer, going by the
                      measured speed, is shortened (the build loops the clip) or drawn in 2D;
                      one that overruns is killed.
    SCENE_3D_TOTAL:   most seconds for all 3D scenes together (default 3600); after that the rest are drawn in 2D.
    """

    def __init__(self, per_scene: float | None = None, total: float | None = None, count: int = 0,
                 folder: Path | None = None) -> None:
        self.per_scene = per_scene if per_scene is not None else _env("SCENE_3D_TIMEOUT", 600)
        self.total = total if total is not None else _env("SCENE_3D_TOTAL", 3600)
        self.count, self.finished, self.spent = count, 0, 0.0
        self.frames_done, self.cancelled = 0, False
        self._t0 = 0.0
        self.folder = folder  # project folder holding the CANCEL flag (None: no cancel)
        self.run: progress.Run | None = None  # where progress is reported
        self.segments = 0
        self.pos, self.fps, self.remaining = 0, 15, 0.0  # scene position, its fps, video seconds of 3D still to come

    @property
    def sec_per_frame(self) -> float | None:
        """Measured seconds per frame so far (None before the first scene has rendered)."""
        return self.spent / self.frames_done if self.frames_done else None

    def seconds_to_render(self, wanted: float, fps: int) -> tuple[float | None, str]:
        """(seconds of video to render in 3D, note). None means draw this scene in 2D; the note says why."""
        self.cancelled = self.cancelled or self.should_stop()
        if self.cancelled:
            return None, "3D rendering was cancelled"
        left = self.total - self.spent
        if left <= 0:
            return None, f"the {fmt_duration(self.total)} 3D time budget is used up"
        spf = self.sec_per_frame
        if spf is None:
            return wanted, ""
        allowed = min(self.per_scene, left)
        fits = allowed / spf / fps
        if fits >= wanted:
            return wanted, ""
        if fits < MIN_SECONDS:
            return None, f"it would take about {fmt_duration(wanted * fps * spf)} (limit {fmt_duration(allowed)})"
        return round(fits, 1), f"shortened from {wanted:.0f} s to {fits:.0f} s to fit {fmt_duration(allowed)}"

    def timeout(self) -> float:
        """Kill limit for the scene about to start."""
        return max(30.0, min(self.per_scene * 1.5, self.total - self.spent + 60))

    def start(self, pos: int, fps: int) -> None:
        """A scene at segment `pos` is about to render."""
        self._t0, self.pos, self.fps = time.monotonic(), pos, fps

    def done(self, frames: int) -> None:
        """Record a finished scene's time and frame count (a reused clip, finished in an instant, is not counted)."""
        took = time.monotonic() - self._t0
        self.finished += 1
        if took >= 2.0:
            self.spent += took
            self.frames_done += frames

    def should_stop(self) -> bool:
        """True when the owner asked to cancel."""
        return bool(self.folder and progress.cancelled(self.folder))

    def on_frame(self, done: int, total: int) -> None:
        """Called while Blender renders: write progress and stop early when the scene is clearly too slow."""
        elapsed = time.monotonic() - self._t0
        eta = self.eta(done, total, self.fps, self.remaining)
        if self.run:
            self.run.step(max(self.pos - 1, 0), f"3D scene {self.finished + 1} of {self.count}",
                          f"segment {self.pos} of {self.segments}, frame {done} of {total}", eta_seconds=eta,
                          frame=done, frames=total, scene=self.finished + 1, scenes=self.count)
        if done >= 8 and elapsed / done * total > self.per_scene * 1.25:
            self.spent += elapsed
            self.frames_done += done  # keep what was learnt about Blender's speed for the next decision
            raise SceneTooSlow("A 3D scene is too slow.", f"At this speed it needs about "
                               f"{fmt_duration(elapsed / done * total)} (limit {fmt_duration(self.per_scene)}).",
                               "It is shortened or drawn in 2D.")

    def eta(self, frames_done_now: int, frames_total_now: int, fps: int, remaining_seconds: float) -> float | None:
        """Seconds left for this scene plus the scenes still to come (at their video lengths)."""
        spf = self.sec_per_frame
        if spf is None:
            elapsed = time.monotonic() - self._t0
            spf = elapsed / frames_done_now if frames_done_now else None
        if spf is None:
            return None
        return (frames_total_now - frames_done_now) * spf + remaining_seconds * fps * spf
