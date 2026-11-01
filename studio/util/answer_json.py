"""Tolerant reader for the JSON answers people paste back from Claude.

Chat answers rarely arrive as clean JSON: they come wrapped in ```json fences, with a sentence before or after,
smart quotes, trailing commas, comments or raw line breaks inside strings. `parse_answer` copes with all of
these and, when it still cannot parse, raises a StudioError that points at the line and column.
"""

from __future__ import annotations

import json
import re

from studio.errors import StudioError

_FENCE = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\r?\n?(.*?)```", re.DOTALL)
_SMART = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'"})
_INVISIBLE = dict.fromkeys(map(ord, "﻿​‌‍⁠ "), " ")


def _clean(text: str) -> str:
    return text.translate(_INVISIBLE).replace("\r\n", "\n").strip()


def _strip_trailing_commas(s: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", s)


def _strip_comments(s: str) -> str:
    """Remove // line comments that are not inside strings (Claude sometimes annotates JSON)."""
    out, in_str, esc, i = [], False, False, 0
    while i < len(s):
        c = s[i]
        if in_str:
            out.append(c)
            esc = (c == "\\" and not esc)
            if c == '"' and not esc:
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and s[i:i + 2] == "//":
            while i < len(s) and s[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _variants(s: str) -> list[str]:
    """The text as given, then progressively more repaired versions of it."""
    v = [s, _strip_trailing_commas(s)]
    v.append(_strip_trailing_commas(_strip_comments(s)))
    v.append(_strip_trailing_commas(_strip_comments(s.translate(_SMART))))
    seen: list[str] = []
    for x in v:
        if x not in seen:
            seen.append(x)
    return seen


def _first_object(s: str) -> tuple[dict | None, str, json.JSONDecodeError | None]:
    """Decode the first JSON object in `s`, ignoring text around it. Returns (obj, text_from_brace, error)."""
    dec = json.JSONDecoder(strict=False)
    first_err: json.JSONDecodeError | None = None
    start = s.find("{")
    while start != -1:
        try:
            obj, _ = dec.raw_decode(s, start)
            if isinstance(obj, dict):
                return obj, s[start:], None
        except json.JSONDecodeError as exc:
            if first_err is None:
                first_err = exc
            # A later "{" may still start the real object (e.g. a stray brace in the intro text); but if the
            # first brace is the answer, a retry from its own text gives the same error, so stop at the first.
            if first_err is exc and s[:start].strip() == "":
                break
        start = s.find("{", start + 1)
    return None, s[s.find("{"):] if "{" in s else s, first_err


def _locate(text: str, err: json.JSONDecodeError) -> str:
    lines = text.splitlines() or [""]
    ln = min(max(err.lineno, 1), len(lines))
    line = lines[ln - 1]
    col = max(err.colno, 1)
    lo = max(col - 40, 0)
    snippet = line[lo:col + 40].strip()
    return f"line {ln}, column {col} (near: “{snippet}”)" if snippet else f"line {ln}, column {col}"


def parse_answer(text: str) -> dict:
    """Parse the first JSON object in a pasted answer, repairing common chat artefacts.

    Raises StudioError saying what is wrong and where when no object can be read.
    """
    raw = _clean(text or "")
    if not raw:
        raise StudioError("The answer is empty.", "Nothing was pasted or uploaded.",
                          "Paste the JSON Claude wrote (everything from { to }), then click Save and apply.")
    if "{" not in raw:
        raise StudioError("The answer has no JSON object in it.",
                          "It should start with { and end with }, but no { was found.",
                          "Ask Claude to reply with ONLY the JSON object described in the request, then paste it.")
    candidates = [m.group(1) for m in _FENCE.finditer(raw) if "{" in m.group(1)] + [raw]
    first_err, err_text = None, raw
    for cand in candidates:
        cand = _clean(cand)
        for variant in _variants(cand):
            obj, rest, err = _first_object(variant)
            if obj is not None:
                return obj
            if err is not None and first_err is None:
                first_err, err_text = err, rest
    if first_err is None:
        raise StudioError("The answer has no complete JSON object.", "A { was found but no matching }.",
                          "The paste is probably cut off. Copy Claude's whole reply, including the last }.")
    rest_trim = err_text
    truncated = first_err.pos >= len(rest_trim) - 2 and rest_trim.count("{") > rest_trim.count("}")
    why = (f"Claude's reply looks cut off: JSON stops at {_locate(rest_trim, first_err)} before it is closed."
           if truncated else f"{first_err.msg} at {_locate(rest_trim, first_err)}.")
    raise StudioError("The pasted answer is not valid JSON, so nothing was saved.", why,
                      "Fix that spot, or ask Claude to reply again with only the JSON object, then paste it again.")


def normalize_answer(text: str) -> str:
    """Pretty, strictly valid JSON text for the response file (raises StudioError like parse_answer)."""
    return json.dumps(parse_answer(text), indent=2, ensure_ascii=False)
