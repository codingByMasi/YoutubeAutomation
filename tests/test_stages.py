import pytest

from studio.errors import StageError
from studio.models import Idea, Video
from studio.stages.base import STAGES, advance, check_can_run, run_stage


def make_video(ctx, stage="approved"):
    idea = Idea(seed="s", topic="t", status="approved")
    ctx.session.add(idea)
    ctx.session.flush()
    v = Video(idea_id=idea.id, stage=stage)
    ctx.session.add(v)
    ctx.session.commit()
    return v


def test_stage_list_matches_spec():
    assert STAGES == ["idea", "approved", "scripted", "voiced", "visuals_ready", "built", "thumbnailed",
                      "reviewed", "scheduled", "live"]


def test_cannot_skip_stages(ctx):
    v = make_video(ctx, "approved")
    with pytest.raises(StageError) as e:
        check_can_run(v, "voiced")
    assert "Run `script" in str(e.value)
    with pytest.raises(StageError):
        advance(v, "built")


def test_next_stage_runs_and_advances(ctx):
    v = make_video(ctx, "scripted")
    calls = []
    r = run_stage(ctx.session, v, "voiced", lambda: calls.append(1))
    assert r.ran and v.stage == "voiced" and calls == [1]


def test_finished_stage_is_noop_without_force(ctx):
    v = make_video(ctx, "built")
    calls = []
    r = run_stage(ctx.session, v, "voiced", lambda: calls.append(1))
    assert not r.ran and "already done" in r.message and calls == [] and v.stage == "built"


def test_force_reruns_and_rolls_stage_back(ctx):
    v = make_video(ctx, "built")
    r = run_stage(ctx.session, v, "voiced", lambda: None, force=True)
    assert r.ran and v.stage == "voiced"


def test_scheduled_video_locks_earlier_stages(ctx):
    v = make_video(ctx, "scheduled")
    with pytest.raises(StageError):
        run_stage(ctx.session, v, "built", lambda: None, force=True)
