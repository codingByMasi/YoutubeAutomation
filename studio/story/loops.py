"""Open loops with ids: every planted loop needs a later payoff, spread across the video, at the right distance."""

from __future__ import annotations


def _ids(v: object) -> list[str]:
    if v in (None, "", []):
        return []
    return [str(x) for x in (v if isinstance(v, list) else [v]) if str(x).strip()]


def starts(segs: list[dict]) -> list[float]:
    """Start second of each segment (real_seconds when present, else est_seconds)."""
    t, out = 0.0, []
    for s in segs:
        out.append(t)
        t += float(s.get("real_seconds") or s.get("est_seconds") or 0)
    return out


def loop_table(segs: list[dict]) -> dict[str, dict]:
    """{loop_id: {plant: seconds|None, pays: [seconds...], plant_seg, pay_segs}} from plants_loop / pays_loop."""
    out: dict[str, dict] = {}
    for i, (t, s) in enumerate(zip(starts(segs), segs), 1):
        for lid in _ids(s.get("plants_loop")):
            out.setdefault(lid, {"plant": None, "pays": [], "pay_segs": []})
            if out[lid]["plant"] is None:
                out[lid].update(plant=t, plant_seg=i)
        for lid in _ids(s.get("pays_loop")):
            e = out.setdefault(lid, {"plant": None, "pays": [], "pay_segs": []})
            e["pays"].append(t)
            e["pay_segs"].append(i)
    return out


def loop_problems(pkg: dict, profile: dict) -> list[str]:
    """Plant/payoff validation. Replaces the old 'open_loop field is non-empty' check."""
    segs = pkg.get("segments") or []
    if not segs:
        return []
    total = sum(float(s.get("real_seconds") or s.get("est_seconds") or 0) for s in segs)
    table = loop_table(segs)
    out: list[str] = []
    if not table:
        return ["no open loops: add plants_loop / pays_loop ids to the segments (plant a question early, pay it off "
                "1-3 minutes later)"]
    dmin, dmax = profile["loop_distance"]
    slack = 15.0
    long_video = total >= 300
    payoffs: list[float] = []
    for lid, e in table.items():
        if e["plant"] is None:
            out.append(f"loop {lid!r} is paid off (segment {e['pay_segs'][0]}) but never planted")
            continue
        later = [p for p in e["pays"] if p > e["plant"]]
        if not later:
            out.append(f"loop {lid!r} planted in segment {e['plant_seg']} has no later payoff (pays_loop)")
            continue
        payoffs.append(later[0])
        dist = later[0] - e["plant"]
        if long_video and not dmin - slack <= dist <= dmax + slack:
            out.append(f"loop {lid!r}: payoff comes {dist:.0f}s after the plant; keep it {dmin:g}-{dmax:g}s "
                       f"(move the payoff to segment ~{_seg_at(segs, e['plant'] + (dmin + dmax) / 2)})")
    planted_early = [e for e in table.values() if e["plant"] is not None and e["plant"] <= 60]
    need = int(profile.get("min_loops_first_60s", 2))
    if len(planted_early) < need:
        out.append(f"only {len(planted_early)} loop(s) planted in the first 60s; need {need}")
    if payoffs and total >= 180 and all(p >= total * 0.8 for p in payoffs):
        out.append("every payoff is in the last 20% of the video; pay some off in the middle to keep viewers")
    return out


def _seg_at(segs: list[dict], second: float) -> int:
    st = starts(segs)
    return max(1, sum(1 for t in st if t <= second))


def loop_map(pkg: dict) -> list[dict]:
    """Loops as [{id, plant_seconds, payoff_seconds}] for reports and the retention heatmap."""
    t = loop_table(pkg.get("segments") or [])
    return [{"id": k, "plant_seconds": round(v["plant"] or 0), "payoff_seconds": round(v["pays"][0]) if v["pays"] else None}  # noqa: E501
            for k, v in t.items()]
