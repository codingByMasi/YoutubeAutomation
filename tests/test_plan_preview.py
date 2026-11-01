"""Plan preview: what will be used, shown and approved before rendering."""

from studio import plan_preview as pp

BAR = {"type": "bar", "title": "Rev", "labels": ["A", "B"], "values": [1, 2], "unit": "$", "source_ids": ["s1"]}


def pkg(**seg):
    base = {"narration": "hello world", "est_seconds": 20, "visual_keywords": ["factory"], "chapter": "Intro"}
    return {"segments": [{**base, **seg}, {**base, "chart_data": BAR}], "sources": []}


def test_rows_list_search_scene_and_chart(ctx):
    plan = pp.build(ctx.settings, 1, pkg(scene={"kind": "timeline", "items": [], "source_ids": ["s1"]}))
    assert plan["segments"][0]["keywords"] == ["factory"]
    assert plan["segments"][0]["scene"]["kind"] == "timeline"
    assert plan["segments"][1]["chart"]["type"] == "bar"
    assert plan["global"]["resolution"].startswith("1920x1080")
    assert any("Blender" in w or "stock" in w.lower() for w in plan["warnings"])


def test_draft_resolution(ctx):
    assert pp.build(ctx.settings, 1, pkg(), draft=True)["global"]["resolution"].startswith("1280x720")


def test_unsourced_chart_is_flagged(ctx):
    p = pkg()
    p["segments"][1]["chart_data"] = {**BAR, "source_ids": []}
    assert any("no source" in w for w in pp.build(ctx.settings, 1, p)["warnings"])


def test_approval_follows_the_plan(ctx):
    ctx.settings.project_dir(1)
    plan = pp.build(ctx.settings, 1, pkg())
    assert not pp.is_approved(ctx.settings, 1, plan)
    pp.approve(ctx.settings, 1, plan)
    assert pp.is_approved(ctx.settings, 1, plan)
    changed = pp.build(ctx.settings, 1, pp.set_keywords(pkg(), 1, ["steel", "mill"]))
    assert not pp.is_approved(ctx.settings, 1, changed)


def test_to_lines(ctx):
    assert any("search: factory" in ln for ln in pp.to_lines(pp.build(ctx.settings, 1, pkg())))
