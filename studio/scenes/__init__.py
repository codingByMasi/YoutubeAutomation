"""Rich scenes for narrated channels: timelines, route maps, 3D-style bar charts and artifact showcases.

A segment in `script.json` may carry an optional `scene`; the owner chooses per channel, per video and per segment
whether it is drawn in 3D (Blender) or as a 2D motion graphic. See `plan` for the rules.
"""

from __future__ import annotations

KINDS = ("timeline", "map", "chart3d", "artifact", "host")
SHAPES = ("coin", "column", "vase", "box")
STYLES = ("", "2d", "3d")  # per-scene / per-segment choice ("" = follow the video, channel and type)
SCENE_STYLES = ("", "2d", "3d", "mixed")  # channel / video choice
MAX_ITEMS = 10
HELP = {
    "timeline": "items: [{label: '1066', text: 'Norman conquest'}, ...] (2-10, in order)",
    "map": "items: [{label: 'Rome', x: 0.2, y: 0.4}, ...] (2-10 places in route order; x, y between 0 and 1)",
    "chart3d": "items come from the segment's bar or line chart_data when left out",
    "artifact": "items: [{label: 'Roman denarius', shape: 'coin|column|vase|box'}] (exactly 1)",
    "host": "action: present|point|celebrate|shock|think|shrug|walk_in|fall|wave; set: studio|vault|street|boardroom|"
            "stage; props: up to 4 of money_stack, bars_up, bars_down, logo_block, vault_door, question_mark, "
            "coin_rain (all optional; the channel mascot is the actor)",
}


def validate_scene(scene: object, where: str, seg: dict | None = None,
                   source_ids: set[str] | None = None) -> list[str]:
    """Problems with a segment's optional `scene` (empty list when fine or absent)."""
    if scene in (None, {}):
        return []
    if not isinstance(scene, dict):
        return [f"{where}: scene must be an object"]
    p: list[str] = []
    kind = scene.get("kind")
    if kind not in KINDS:
        return [f"{where}: scene kind {kind!r} not in {list(KINDS)}"]
    if scene.get("style", "") not in STYLES:
        p.append(f"{where}: scene style {scene.get('style')!r} not in ['', '2d', '3d']")
    if kind == "host":
        from studio.scenes import host

        return p + host.validate(scene, where) + [f"{where}: scene cites unknown source id {r!r}"
                                                  for r in scene.get("source_ids") or []
                                                  if source_ids is not None and str(r) not in source_ids]
    refs = scene.get("source_ids") or []
    for r in refs:
        if source_ids is not None and str(r) not in source_ids:
            p.append(f"{where}: scene cites unknown source id {r!r}")
    if kind == "timeline" and not refs:
        p.append(f"{where}: a timeline needs source_ids (every date needs a source)")
    items = scene.get("items")
    if kind == "chart3d" and not items:
        chart = (seg or {}).get("chart_data") or {}
        if chart.get("type") not in ("bar", "line"):
            p.append(f"{where}: a chart3d scene needs items or a bar/line chart_data on the same segment")
        return p
    if not isinstance(items, list) or not items:
        return p + [f"{where}: {kind} scene needs items ({HELP[kind]})"]
    if len(items) > MAX_ITEMS:
        p.append(f"{where}: {kind} scene has {len(items)} items; use at most {MAX_ITEMS}")
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict) or not str(it.get("label", "")).strip():
            p.append(f"{where}: scene item {i} needs a label")
            continue
        if kind == "map":
            for axis in ("x", "y"):
                v = it.get(axis)
                if not isinstance(v, (int, float)) or not 0 <= v <= 1:
                    p.append(f"{where}: map item {i} needs {axis} between 0 and 1")
        if kind == "chart3d" and not isinstance(it.get("value"), (int, float)):
            p.append(f"{where}: chart3d item {i} needs a numeric value")
    if kind == "chart3d" and not refs:
        p.append(f"{where}: a chart3d scene with its own items needs source_ids (every figure needs a source)")
    if kind in ("timeline", "map") and isinstance(items, list) and len(items) < 2:
        p.append(f"{where}: a {kind} needs at least 2 items")
    if kind == "artifact" and isinstance(items, list):
        if len(items) != 1:
            p.append(f"{where}: an artifact scene shows exactly 1 item")
        elif items[0].get("shape", "coin") not in SHAPES:
            p.append(f"{where}: artifact shape {items[0].get('shape')!r} not in {list(SHAPES)}")
    return p


def chart_items(seg: dict) -> list[dict]:
    """Bar, line and pie chart_data as chart3d items ([] for flow and number charts)."""
    chart = seg.get("chart_data") or {}
    if chart.get("type") not in ("bar", "line", "pie"):
        return []
    from studio.providers.charts import fmt

    unit = chart.get("unit", "")
    return [{"label": str(lab), "value": float(v), "display": fmt(v, unit)}
            for lab, v in zip(chart.get("labels", []), chart.get("values", []), strict=False)][:MAX_ITEMS]


def plan_for(seg: dict, pos: int, prod: dict) -> dict | None:
    """`plan` for segment `pos` with the video's resolved settings, including automatic host-character scenes.

    When the channel has a mascot, host scenes are on ("auto", the default) and the scene style is 3d/mixed, every
    other segment without its own scene or chart is acted out by the mascot (position 1 always is).
    """
    override = prod["segment_styles"].get(pos, "")
    pl = plan(seg, prod["scene_style"], override)
    if pl:
        if pl["scene"]["kind"] == "host" and not pl["scene"].get("mascot") and prod.get("mascot"):
            pl["scene"] = {**pl["scene"], "mascot": dict(prod["mascot"])}
        return pl
    mascot, mode = prod.get("mascot"), override or prod["scene_style"]
    if (mascot and prod.get("host", "auto") == "auto" and mode in ("3d", "mixed") and not seg.get("scene")
            and not seg.get("chart_data") and (pos == 1 or pos % 2 == 1)):
        from studio.scenes import host

        return {"scene": host.make_scene(seg, pos, mascot), "mode": "3d"}
    return None


def plan(seg: dict, style: str, override: str = "") -> dict | None:
    """What to draw for a segment: {"scene": {...}, "mode": "2d" | "3d"}, or None for the normal visuals.

    style:    the video's/channel's choice. "2d": scenes are drawn as 2D motion graphics. "3d" and "mixed": scenes are
              3D and every bar, line and pie chart becomes a 3D chart too (so a script with no scenes still gets 3D);
              flow and number charts stay 2D.
    override: this segment's own choice ("2d" or "3d"); it also beats the scene's own `style`.
    A chart3d scene in 2D mode needs nothing extra: the regular 2D chart is its equivalent.
    """
    scene = seg.get("scene") or None
    seg_style = override or (scene or {}).get("style", "")
    if scene is None:
        items = chart_items(seg)
        if not items or not (seg_style == "3d" or (not seg_style and style in ("3d", "mixed"))):
            return None
        scene = {"kind": "chart3d", "title": (seg.get("chart_data") or {}).get("title", "")}
    scene = dict(scene)
    if scene["kind"] == "chart3d" and not scene.get("items"):
        scene["items"] = chart_items(seg)
    mode = seg_style or ("2d" if style in ("", "2d") else "3d")
    if scene["kind"] == "chart3d" and mode == "2d":
        return None
    return {"scene": scene, "mode": mode}
