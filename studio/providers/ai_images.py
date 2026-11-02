"""Pluggable AI-image provider interface. The default is `none`: nothing is generated and nothing needs a GPU.

Keys (all optional): AI_IMAGE_PROVIDER = none | comfyui | diffusers; COMFYUI_URL (default http://127.0.0.1:8188);
DIFFUSERS_MODEL (a Hugging Face model id). A generated image makes the video `synthetic_media`: the studio then adds
the required altered-or-synthetic-content disclosure at upload time (never silently hidden).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Protocol


class AIImageProvider(Protocol):
    name: str

    def available(self) -> bool: ...
    def generate(self, prompt: str, out: Path, size: tuple[int, int] = (1920, 1080)) -> Path | None: ...


class NullProvider:
    """No image generation (default)."""

    name = "none"

    def available(self) -> bool:
        return False

    def generate(self, prompt: str, out: Path, size: tuple[int, int] = (1920, 1080)) -> Path | None:
        return None


class ComfyUIProvider:
    """Talks to a ComfyUI server you run yourself. Not implemented beyond a reachability check: workflows are
    user-specific, so `generate` returns None until a workflow file is configured (COMFYUI_WORKFLOW)."""

    name = "comfyui"

    def __init__(self, url: str = "http://127.0.0.1:8188") -> None:
        self.url = url

    def available(self) -> bool:
        import urllib.request
        try:
            urllib.request.urlopen(self.url + "/system_stats", timeout=2)
            return bool(os.getenv("COMFYUI_WORKFLOW"))
        except Exception:  # noqa: BLE001
            return False

    def generate(self, prompt: str, out: Path, size: tuple[int, int] = (1920, 1080)) -> Path | None:
        return None  # adapter point: queue the workflow, wait, download to `out`


class DiffusersProvider:
    """Hugging Face diffusers. Only enabled when torch sees a GPU; never required."""

    name = "diffusers"

    def __init__(self, model: str) -> None:
        self.model = model

    def available(self) -> bool:
        if not self.model or importlib.util.find_spec("diffusers") is None or importlib.util.find_spec("torch") is None:
            return False
        import torch
        return bool(torch.cuda.is_available())

    def generate(self, prompt: str, out: Path, size: tuple[int, int] = (1920, 1080)) -> Path | None:
        import torch
        from diffusers import AutoPipelineForText2Image
        pipe = AutoPipelineForText2Image.from_pretrained(self.model, torch_dtype=torch.float16).to("cuda")
        pipe(prompt, width=size[0] // 2, height=size[1] // 2).images[0].resize(size).save(out)
        return out


def make_ai_images() -> AIImageProvider:
    """Provider from AI_IMAGE_PROVIDER; anything unavailable degrades to the null provider."""
    name = (os.getenv("AI_IMAGE_PROVIDER") or "none").strip().lower()
    prov: AIImageProvider = NullProvider()
    if name == "comfyui":
        prov = ComfyUIProvider(os.getenv("COMFYUI_URL", "http://127.0.0.1:8188"))
    elif name == "diffusers":
        prov = DiffusersProvider(os.getenv("DIFFUSERS_MODEL", ""))
    return prov if prov.available() else NullProvider()
