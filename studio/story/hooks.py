"""Hook variants: deterministic scoring, rotation against recent videos, and picking the best one."""

from __future__ import annotations

from studio.story import ledger

RUBRIC = ("curiosity", "clarity", "stakes", "promise")  # LLM scores, 1-5 each


def _pkg_for(line: str, hook_type: str, seconds: float | None = None) -> dict:
    n = len(line.split())
    return {"hook_type": hook_type, "segments": [{"narration": line, "est_seconds": seconds or max(3.0, n / 2.5)}]}


def det_score(line: str, hook_type: str, gate_type: str = "explainer") -> tuple[int, list[str]]:
    """0-100 from the quality gate's own hook check (the same rules the final gate applies)."""
    from studio.quality import gate, profiles
    t = profiles.thresholds(gate_type)
    found = gate.check_hook(_pkg_for(line, hook_type), t)
    pen = {"critical": 45, "major": 22, "minor": 8}
    return max(0, 100 - sum(pen[i["severity"]] for i in found)), [i["text"] for i in found]


def llm_score(variant: dict) -> float | None:
    """Average rubric score scaled to 0-100, or None if the model gave none."""
    sc = variant.get("score") or {}
    vals = [sc[k] for k in RUBRIC if isinstance(sc.get(k), (int, float))]
    return round(sum(vals) / len(vals) * 20, 1) if len(vals) == len(RUBRIC) else None


def validate_variants(variants: object, profile: dict, count: int = 8) -> list[str]:
    """Shape and formula problems in the hook variants of the story_plan answer."""
    if not isinstance(variants, list) or len(variants) != count:
        return [f"hooks must be a list of exactly {count} variants (got {len(variants) if isinstance(variants, list) else 0})"]
    problems = []
    allowed = set(profile["hook_formulas"])
    for i, v in enumerate(variants, 1):
        if v.get("hook_type") not in allowed:
            problems.append(f"hook {i}: hook_type {v.get('hook_type')!r} not in {sorted(allowed)}")
        if not str(v.get("line", "")).strip():
            problems.append(f"hook {i}: line is empty")
        if llm_score(v) is None:
            problems.append(f"hook {i}: score needs integers 1-5 for {list(RUBRIC)}")
    if len({v.get("hook_type") for v in variants}) < min(4, len(allowed)):
        problems.append(f"use at least {min(4, len(allowed))} different hook_type values across the variants")
    return problems


def rank(variants: list[dict], recent_types: list[str], profile: dict) -> list[dict]:
    """Variants with det_score, llm_score, total and `blocked` (rotation) filled in, best first."""
    out = []
    for v in variants:
        d, why = det_score(str(v.get("line", "")), str(v.get("hook_type", "")), profile.get("gate_type", "explainer"))
        l = llm_score(v)
        total = round((d + l) / 2, 1) if l is not None else float(d)
        out.append({**v, "det_score": d, "det_notes": why, "llm_score": l, "total": total,
                    "blocked": v.get("hook_type") in recent_types})
    return sorted(out, key=lambda x: (x["blocked"], -x["total"]))


def pick_best(variants: list[dict], recent_types: list[str], profile: dict) -> tuple[dict, list[dict]]:
    """(chosen variant, all ranked). Variants whose hook_type was in the last 3 videos lose to any unblocked one."""
    ranked = rank(variants, recent_types, profile)
    return ranked[0], ranked


def rotation_problem(hook_type: str, root, n: int = 3, exclude_video: int | None = None) -> str | None:
    """A message if hook_type was used in the channel's last n videos."""
    recent = ledger.recent_hook_types(root, n, exclude_video)
    if hook_type and hook_type in recent:
        return (f"hook_type {hook_type!r} was used in the last {n} videos ({', '.join(recent)}); "
                "pick a different formula")
    return None
