"""Captions: faster-whisper transcription when installed, otherwise timed from the script text."""

from __future__ import annotations

from pathlib import Path

from studio.util.logging import get_logger

log = get_logger("captions")
Cue = tuple[float, float, str]
MAX_WORDS, MAX_CHARS = 8, 42


def _chunks(text: str) -> list[str]:
    out, cur = [], []
    for w in text.split():
        if cur and (len(cur) >= MAX_WORDS or len(" ".join(cur + [w])) > MAX_CHARS):
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
        if w.endswith((".", "?", "!")) and len(cur) >= 3:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def script_cues(spans: list[tuple[float, float]], narrations: list[str]) -> list[Cue]:
    """Cues from the narration, timed in proportion to word count within each segment."""
    cues: list[Cue] = []
    for (start, end), text in zip(spans, narrations):
        chunks = _chunks(text)
        words = sum(len(c.split()) for c in chunks) or 1
        t = start
        for c in chunks:
            d = (end - start) * len(c.split()) / words
            cues.append((round(t, 3), round(t + d, 3), c))
            t += d
    return cues


def cues_from_words(words: list[tuple[float, float, str]]) -> list[Cue]:
    """Subtitle-sized cues (SRT for upload) from per-word times."""
    cues: list[Cue] = []
    cur: list = []
    for w in words:
        cur.append(w)
        text = " ".join(x[2] for x in cur)
        if len(cur) >= MAX_WORDS or len(text) > MAX_CHARS or w[2].endswith((".", "?", "!")):
            cues.append((cur[0][0], cur[-1][1], text))
            cur = []
    if cur:
        cues.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
    return cues


def _decode_16k(audio: Path):
    """Mono 16 kHz float samples via ffmpeg.

    faster-whisper's own decoder uses PyAV, and newer PyAV releases reject an argument it passes
    ("open() got an unexpected keyword argument 'metadata_errors'"). ffmpeg is already required, so use it.
    """
    import subprocess

    import numpy as np

    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(audio), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def whisper_cues(audio: Path, model_size: str = "small") -> list[Cue] | None:
    """Word-timed cues from faster-whisper, or None if it is not installed."""
    words = whisper_words(audio, model_size)
    return None if words is None else cues_from_words(words)


def whisper_words(audio: Path, model_size: str = "small") -> list[tuple[float, float, str]] | None:
    """Per-word (start, end, text) from faster-whisper, or None if it is not installed."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    def run(device: str, compute: str) -> list[tuple[float, float, str]]:
        model = WhisperModel(model_size, device=device, compute_type=compute)
        segments, _ = model.transcribe(_decode_16k(audio), word_timestamps=True, language="en")
        return [(w.start, w.end, w.word.strip()) for s in segments for w in (s.words or []) if w.word.strip()]

    if cuda_status()["on_gpu"]:
        try:
            return run("cuda", "float16")
        except RuntimeError as exc:  # missing/odd CUDA libraries show up only at the first real transcribe
            log.warning("Whisper on the GPU failed (%s); using the CPU.", exc)
    return run("cpu", "int8")


_CUDA_LIBS = {"nt": ("cublas64_12.dll", "cudnn64_9.dll"), "posix": ("libcublas.so.12", "libcudnn.so.9")}


def _load_cuda_libs() -> str | None:
    """Try to load the NVIDIA libraries Whisper needs on a GPU. Returns the first one missing, else None."""
    import ctypes
    import importlib.util
    import os

    spec = importlib.util.find_spec("nvidia")  # the pip packages nvidia-cublas-cu12 / nvidia-cudnn-cu12
    for base in (list(spec.submodule_search_locations or []) if spec else []):
        for sub in Path(base).glob("*/bin" if os.name == "nt" else "*/lib"):
            if os.name == "nt":
                os.add_dll_directory(str(sub))
                os.environ["PATH"] = f"{sub}{os.pathsep}{os.environ.get('PATH', '')}"
            else:
                for so in sub.glob("*.so*"):
                    try:
                        ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass
    for name in _CUDA_LIBS.get(os.name, ()):
        try:
            ctypes.CDLL(name)
        except OSError:
            return name
    return None


_cuda_cache: dict | None = None


def cuda_status(refresh: bool = False) -> dict:
    """Does Whisper really run on the graphics card here? {gpu, on_gpu, problem, message}.

    `gpu` = an NVIDIA card is visible; `on_gpu` = captions will use it; `problem` = a card is there but cannot be used
    (the studio then uses the CPU, which is slower but works). Never raises.
    """
    global _cuda_cache
    if _cuda_cache is not None and not refresh:
        return _cuda_cache
    try:
        import ctranslate2
        gpu = ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - not installed or no CUDA build: simply no GPU path
        gpu = False
    if not gpu:
        res = {"gpu": False, "on_gpu": False, "problem": False,
               "message": "Captions are made on the CPU (no NVIDIA graphics card was found for it)."}
    elif (missing := _load_cuda_libs()) is not None:
        res = {"gpu": True, "on_gpu": False, "problem": True,
               "message": "Your graphics card could make captions much faster, but NVIDIA's helper files "
                          f"({missing} and friends) are not installed, so the CPU is being used instead. "
                          "Fix this installs them (a large one-time download, about 1 GB)."}
    else:
        res = {"gpu": True, "on_gpu": True, "problem": False, "message": "Captions are made on your graphics card."}
    _cuda_cache = res
    return res


def ts(seconds: float) -> str:
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue], offset: float = 0.0, window: tuple[float, float] | None = None) -> str:
    """SRT text; `offset` shifts every cue, `window` keeps only cues inside (start, end) re-based to 0."""
    lines, n = [], 0
    for start, end, text in cues:
        if window:
            if end <= window[0] or start >= window[1]:
                continue
            start, end = max(start, window[0]) - window[0], min(end, window[1]) - window[0]
        n += 1
        lines.append(f"{n}\n{ts(start + offset)} --> {ts(end + offset)}\n{text}\n")
    return "\n".join(lines)
