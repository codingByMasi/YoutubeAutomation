"""Owner decision: no prompt for any channel asks for sources, citations or fact ids."""

from __future__ import annotations

import pytest

from studio.growth import channel_types, channels
from studio.stages import discover
from studio.stages import script as sc
from studio.story import profile as sp
from studio.story import prompts, style
from studio.web import service as svc

TASKS = ["script", "outline", "critique", "story_plan", "story_review"]


def test_detector_catches_the_old_wording():
    for bad in ("cite sources", "with its source id", "`fact_ids`", "give `source_url`", "Sources are optional"):
        assert prompts.asks_for_sources(bad), bad
    assert not prompts.asks_for_sources("Use real figures; word estimates as estimates.")


@pytest.mark.parametrize("pack", ["explainer", "history", "kids", "general"])
@pytest.mark.parametrize("task", TASKS)
def test_every_pack_template_is_free_of_source_asks(pack, task):
    text = prompts.compose(task, sp.get(pack), topic="t", brief="b", style=style.for_profile(sp.get(pack), ""),
                           outline="{}", draft="{}", facts="{}", plan="{}", script="{}", audience="a",
                           language="English", region="r", beat_sheet="x", hook_formulas="y", hook_words=12,
                           fact_count="8-14", learned="", competitors="", facts_note="")
    assert not prompts.asks_for_sources(text), (pack, task, prompts.SOURCE_ASK.search(text).group(0))


@pytest.mark.parametrize("ctype", list(channel_types.TYPES))
def test_script_prompt_and_channel_text_for_each_channel_type(ctx, ctype):
    root = ctx.settings.root
    channels.add(root, f"Chan {ctype}", type=ctype, niche="Test niche", audience="Everyone")
    assert not prompts.asks_for_sources(sc.build_prompt(root, "How a shop makes money"))
    p = channels.get(root)
    assert not prompts.asks_for_sources(channels.summary(p))
    assert not prompts.asks_for_sources(channel_types.TYPES[ctype]["guidance"])


def test_topic_research_prompt_has_no_source_ask(ctx):
    assert not prompts.asks_for_sources(discover.ideas_prompt(ctx, 5))


def test_old_saved_prompt_is_dropped_so_it_is_regenerated(ctx):
    d = ctx.settings.project_dir(1)
    pf, rf = svc.prompt_paths(d, "script")
    pf.write_text("Write it.\nEvery figure needs a public source; add `sources`.\n"
                  "\n---\n\n## How to answer\n\nwrite JSON", encoding="utf-8")
    assert svc.read_prompt(ctx, 1) == ""
    assert not pf.exists()
    pf.write_text("Write it. Use real figures.\n\n---\n\n## How to answer\n\nwrite JSON", encoding="utf-8")
    assert "Use real figures" in svc.read_prompt(ctx, 1)
