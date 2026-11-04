"""Voicebanks the sung-melody step may use: only ones whose licence allows monetised videos, with the licence shown.

Every entry was read from the creator's own page on the date in `checked`. Terms can change, so the build
saves a licence note next to the song; re-read the source page before you publish.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio.errors import StudioError


@dataclass(frozen=True)
class Voicebank:
    key: str
    name: str
    source: str  # creator's page (the licence lives here)
    download: str
    licence: str  # short plain-language summary
    credit: str  # line to put in the video description
    warnings: tuple[str, ...]
    checked: str
    monetisation: str = "allowed_with_credit"  # key into MONETISATION_LABEL
    ai_warning: bool = False  # terms ban AI-generated content: needs the creator's OK before monetising


MONETISATION_LABEL = {
    "allowed_with_credit": "Monetising allowed (credit required)",
}

VOICEBANKS: dict[str, Voicebank] = {
    "ayaluna-english": Voicebank(
        key="ayaluna-english",
        name="AyaLuna (English, CVVC)",
        source="https://ayalunautau.carrd.co/",
        download="https://www.mediafire.com/file/8xwr06n57tf3s8s/AyaLuna_english.zip/file",
        licence="Free. Songs and videos made with it may be monetised if the voicebank is credited. "
                "No merchandise, no political/religious/hate use, only the creator may modify it for profit.",
        credit="Vocals: AyaLuna UTAU (https://ayalunautau.carrd.co/)",
        warnings=("The terms ban work that \"uses AI generated content of any kind\". This studio writes scripts "
                  "with an AI model, so ask the creator (@AyaLunaPNG) whether that is allowed before you monetise.",
                  "The terms do not mention kids content, and they may change without warning."),
        checked="2026-11-03",
        monetisation="allowed_with_credit",
        ai_warning=True,
    ),
}


def get(key: str) -> Voicebank:
    """The vetted voicebank for `key`; anything not on the list is refused (not known to allow monetising)."""
    vb = VOICEBANKS.get(key.strip().lower())
    if vb is None:
        raise StudioError(f"Voicebank '{key}' is not on the approved list.",
                          "Only voicebanks whose licence was checked for monetised use can be selected.",
                          "Run `kids voicebanks` to see the list, or ask for a new one to be checked.")
    return vb


def licence_note(vb: Voicebank) -> str:
    lines = [f"Voicebank: {vb.name}", f"Licence checked: {vb.checked}", f"Terms: {vb.source}", "",
             vb.licence, "", f"Credit line for the description: {vb.credit}", ""]
    lines += [f"WARNING: {w}" for w in vb.warnings]
    return "\n".join(lines) + "\n"


def write_licence(vb: Voicebank, sung_dir: Path) -> Path:
    sung_dir.mkdir(parents=True, exist_ok=True)
    path = sung_dir / "VOICEBANK_LICENCE.txt"
    path.write_text(licence_note(vb), encoding="utf-8")
    return path


def monetisation_label(vb: Voicebank) -> str:
    """Plain-language monetisation status for the Voices screen."""
    return MONETISATION_LABEL.get(vb.monetisation, "Unknown: do not monetise")


def singer_dirs(openutau_exe: Path | None) -> list[Path]:
    """Folders where OpenUtau keeps installed voicebanks (next to the app, and in the user's data folder)."""
    import os

    dirs = []
    if openutau_exe is not None:
        dirs.append(openutau_exe.parent / "Singers")
    for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
        if base:
            dirs.append(Path(base) / "OpenUtau" / "Singers")
    return dirs


def is_installed(vb: Voicebank, openutau_exe: Path | None) -> bool:
    """True when a folder named like the voicebank (e.g. 'AyaLuna') sits in an OpenUtau Singers folder."""
    needle = vb.name.split(" ")[0].lower()
    return any(d.is_dir() and any(needle in c.name.lower() for c in d.iterdir()) for d in singer_dirs(openutau_exe))
