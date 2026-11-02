"""Story-engine checks for the quality gate: deterministic, profile-driven, with specific fixes."""

from __future__ import annotations

from studio.story import checks, ledger, loops, safety, titles
from studio.story import facts as facts_mod
from studio.story.profile import enabled


def _i(dim: str, sev: str, text: str, fix: str) -> dict:
    return {"dimension": dim, "severity": sev, "text": text, "fix": fix}


def story_issues(pkg: dict, prof: dict, peers: list[tuple[str, dict]] | None = None,
                 facts: list[dict] | None = None, caption_sync: list[dict] | None = None) -> dict[str, list[dict]]:
    """{dimension: [issue]} for word counts, sentences, loops, figures, hook rotation, repetition, title promise."""
    out: dict[str, list[dict]] = {"script": [], "hook": [], "pacing": [], "originality": [], "metadata": [],
                                  "captions": []}
    segs = pkg.get("segments") or []
    if not segs:
        return out
    engine = bool(pkg.get("engine"))  # scripts from the classic path only get advisory (minor) story checks
    sev = (lambda s: s) if engine else (lambda s: "minor")  # noqa: E731
    if enabled(prof, "word_count_check"):
        out["script"] += [_i("script", sev("major"), p, "Rewrite so words match est_seconds and the target length.")
                          for p in checks.wordcount_problems(pkg, prof)]
    if enabled(prof, "sentence_rules"):
        out["script"] += [_i("script", sev("major"), p, "Split long sentences, vary the rhythm.")
                          for p in checks.sentence_problems(pkg, prof)]
        out["script"] += [_i("script", "critical", p, "Reword it.") for p in checks.banned_problems(pkg, prof)]
        out["script"] += [_i("script", "minor", p, "Use plainer words.") for p in checks.readability_problems(pkg, prof)]  # noqa: E501
    if enabled(prof, "loop_ids") and not prof.get("kids") and engine:
        out["pacing"] += [_i("pacing", "major", p, "Fix plants_loop / pays_loop ids and distances.")
                          for p in loops.loop_problems(pkg, prof)]
    if facts is not None and enabled(prof, "fact_ledger") and engine:
        out["script"] += [_i("script", "major", p, "Cite a fact id or reword as an estimate.")
                          for p in facts_mod.trace_problems(pkg, facts)]
    if enabled(prof, "title_judge") and not prof.get("kids"):
        out["metadata"] += [_i("metadata", sev("major"), p, "Align the opening with the title.")
                            for p in titles.promise_problems(pkg)]
    out["script"] += [_i("script", i["severity"], i["text"], i["fix"]) for i in safety.text_issues(pkg, prof)]
    if enabled(prof, "repetition_ledger") and peers:
        mine = ledger.entry_from_package(pkg)
        others = [ledger.entry_from_package(p) for _, p in reversed(peers)]  # oldest first
        for iss in ledger.repetition_issues(mine, others):
            out["originality"].append(_i("originality", iss["severity"] if engine else "minor", iss["text"], iss["fix"]))  # noqa: E501
    if enabled(prof, "caption_sync_check") and caption_sync:
        drift = [c for c in caption_sync if c.get("drift_ms", 0) > prof["caption_drift_ms"]]
        if drift:
            worst = max(drift, key=lambda c: c["drift_ms"])
            out["captions"].append(_i("captions", "major", f"{len(drift)} caption(s) drift more than "
                                      f"{prof['caption_drift_ms']} ms from the audio (worst {worst['drift_ms']:.0f} ms "
                                      f"in segment {worst.get('segment')}).", "Re-run `voice --force` to re-align."))
    return out
