"""ffmpeg command for mixing a sung vocal over a background bed. Pure: builds the command, runs nothing."""

from __future__ import annotations

from pathlib import Path

MIN_TEMPO, MAX_TEMPO = 0.75, 1.5  # beyond this the voice sounds unnatural, so we stop stretching and trim/pad


def sung_mix_cmd(video: Path, bed: Path, vocal: Path, out: Path, video_s: float,
                 vocal_s: float) -> tuple[list[str], str]:
    """(command, note). The vocal is sped up or slowed down to fit the video length within sane limits.

    The video's narration is dropped (the vocal sings the same words); the bed is looped under the vocal.
    """
    ratio = vocal_s / video_s if video_s > 0 and vocal_s > 0 else 1.0
    tempo = min(MAX_TEMPO, max(MIN_TEMPO, ratio))
    note = ""
    if abs(tempo - ratio) > 1e-6:
        note = (f"Sung vocal is {vocal_s:.0f}s but the video is {video_s:.0f}s; stretched only to x{tempo:.2f}, "
                "so the ending is trimmed or silent. Shorten or lengthen the song in OpenUtau (tempo) to match.")
    graph = (f"[2:a]atempo={tempo:.4f},apad[v];[1:a]volume=-18dB[m];"
             "[v][m]amix=inputs=2:duration=first:normalize=0[a]")
    cmd = ["ffmpeg", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(bed), "-i", str(vocal),
           "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-t", f"{video_s:.3f}", "-c:v", "copy",
           "-c:a", "aac", "-movflags", "+faststart", str(out)]
    return cmd, note
