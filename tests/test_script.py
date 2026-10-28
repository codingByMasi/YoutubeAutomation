import copy
import json
from pathlib import Path

import pytest

from studio.errors import PendingLLMResponse
from studio.models import Idea, Script, Segment, Title, Video
from studio.stages import script as sc

SAMPLE = json.loads((Path(__file__).parent.parent / "studio" / "samples" / "sample_script.json").read_text())


def pkg():
    return copy.deepcopy(SAMPLE)


@pytest.mark.parametrize("title,ok", [
    ("How Cruise Lines Make Money", True),
    ("x" * 69, True),
    ("x" * 70, False),
    ("You Won't Believe How Hotels Make Money", False),
    ("The SHOCKING Truth About Airlines", False),
    ("HOW NETFLIX MAKES MONEY", False),
    ("How the NBA Makes Money", True),  # short acronyms are fine
    ("Guaranteed Profits in Quick Commerce", False),
])
def test_title_validation(title, ok):
    assert (sc.validate_title(title) == []) is ok


def test_sample_package_is_valid():
    assert sc.validate_package(pkg()) == []


def test_title_count_and_single_pick():
    d = pkg()
    d["titles"] = d["titles"][:14]
    assert any("exactly 15" in p for p in sc.validate_package(d))
    d = pkg()
    d["titles"][1]["is_pick"] = True
    assert any("exactly one title" in p for p in sc.validate_package(d))


def test_segment_structure_rules():
    d = pkg()
    d["segments"][0]["est_seconds"] = 30
    d["segments"][1]["visual_keywords"] = []
    d["segments"][2]["chart_data"]["source_ids"] = []
    d["segments"][3]["chart_data"]["source_ids"] = ["nope"]
    d["segments"][4]["narration"] = "This is guaranteed to work."
    problems = "\n".join(sc.validate_package(d))
    for expected in ("hook", "visual_keywords is empty", "chart has no source", "unknown source id", "banned phrase"):
        assert expected in problems


def test_chart_shape_rules():
    assert sc.validate_chart({"type": "bar", "labels": ["a"], "values": [1, 2], "source_ids": ["s"]}, {"s"}, "x")
    assert sc.validate_chart({"type": "number", "labels": ["a"], "values": [1], "source_ids": ["s"]}, {"s"}, "x") == []
    assert sc.validate_chart({"type": "pie3d", "labels": ["a"], "values": [1], "source_ids": ["s"]}, {"s"}, "x")


def test_pacing_warnings_flag_gaps_and_length():
    segs = [{"est_seconds": 60, "beat": "question", "chart_data": {"x": 1}}] + \
           [{"est_seconds": 60, "beat": None, "chart_data": None}] * 3
    warns = "\n".join(sc.pacing_warnings(segs))
    assert "outside 10-15 min" in warns and "retention beat" in warns and "chart" in warns


def test_timeline_prefers_real_seconds():
    assert sc.timeline([{"est_seconds": 10, "real_seconds": 12.5}, {"est_seconds": 5}]) == [(0, 12.5), (12.5, 17.5)]


def approved_video(ctx):
    idea = Idea(seed="coffee", topic="how coffee shops make money", status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage="approved")
    ctx.session.add(v)
    ctx.session.commit()
    return idea, v


def test_script_handoff_then_save(ctx):
    idea, v = approved_video(ctx)
    with pytest.raises(PendingLLMResponse):
        sc.run(ctx, idea.id)
    prompt = (ctx.settings.project_dir(v.id) / "prompts" / "script.prompt.md").read_text()
    assert "how coffee shops make money" in prompt and "exactly 15" in prompt
    assert v.stage == "approved"
    (ctx.settings.project_dir(v.id) / "prompts" / "script.response.json").write_text(json.dumps(pkg()))
    sc.run(ctx, idea.id)
    assert v.stage == "scripted"
    assert ctx.session.query(Title).filter_by(video_id=v.id).count() == 15
    assert ctx.session.query(Title).filter_by(video_id=v.id, is_pick=True).one().text.startswith("How a Coffee")
    assert ctx.session.query(Segment).filter_by(video_id=v.id).count() == 6
    assert ctx.session.query(Script).filter_by(video_id=v.id).one().word_count > 50
    out = ctx.settings.project_dir(v.id)
    assert (out / "script.md").read_text().startswith("# How a Coffee Shop")
    # idempotent: a second run changes nothing
    before = (out / "script.json").stat().st_mtime_ns
    sc.run(ctx, idea.id)
    assert (out / "script.json").stat().st_mtime_ns == before
    assert ctx.session.query(Script).filter_by(video_id=v.id).count() == 1
