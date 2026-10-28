from studio.models import Idea, Video
from studio.stages import research as r
from studio.stages.research import VideoStat, is_outlier, outlier_ratio, score_topic


def test_outlier_ratio_and_small_channel_flag():
    assert outlier_ratio(500_000, 50_000) == 10
    assert outlier_ratio(100, 0) == 100  # hidden subscriber count
    assert is_outlier(500_000, 50_000)            # small channel, 10x
    assert not is_outlier(5_000_000, 2_000_000)   # big channel
    assert not is_outlier(50_000, 40_000)         # small but only 1.25x


def test_topic_with_outliers_and_low_competition_ranks_higher():
    videos = [
        VideoStat("How Cruise Lines Make Money", 2_000_000, 40_000),
        VideoStat("Cruise ship economics explained", 900_000, 30_000),
        VideoStat("How Netflix makes money", 3_000_000, 5_000_000),
        VideoStat("Netflix business model", 2_500_000, 3_000_000),
    ]
    cruise = score_topic("how cruise lines make money", 1, 4, videos)
    netflix = score_topic("netflix business model", 1, 4, videos)
    assert cruise["outlier"] > 0 and netflix["outlier"] == 0
    assert cruise["competition"] < netflix["competition"]
    ideas = [Idea(topic="n", seed="s", demand_score=netflix["demand"], competition_score=netflix["competition"],
                  outlier_score=netflix["outlier"]),
             Idea(topic="c", seed="s", demand_score=cruise["demand"], competition_score=cruise["competition"],
                  outlier_score=cruise["outlier"])]
    assert [i.topic for i in r.rank(ideas)] == ["c", "n"]


def test_no_videos_still_scores_by_suggestion_position():
    assert score_topic("x y", 0, 4, [])["demand"] > score_topic("x y", 3, 4, [])["demand"]


def fake_sources(calls):
    def suggest(seed):
        calls.append("suggest")
        return [seed, "how hotels make money", "hotel business model"]

    def competitors(ctx, seed):
        calls.append("yt")
        return [VideoStat("How hotels make money", 800_000, 20_000)]
    return suggest, competitors


def test_research_saves_ranked_ideas_and_is_idempotent(ctx):
    calls = []
    s, c = fake_sources(calls)
    first = r.run(ctx, "hotel economics", suggest=s, competitors=c)
    assert len(first) == 3 and ctx.session.query(Idea).count() == 3
    second = r.run(ctx, "hotel economics", suggest=s, competitors=c)
    assert calls == ["suggest", "yt"]  # second run used today's cache: no API calls
    assert [i.id for i in second] == [i.id for i in first]
    r.run(ctx, "hotel economics", force=True, suggest=s, competitors=c)
    assert ctx.session.query(Idea).count() == 3  # duplicates skipped


def test_approve_creates_video_once(ctx):
    calls = []
    s, c = fake_sources(calls)
    ideas = r.run(ctx, "hotels", suggest=s, competitors=c)
    v1 = r.approve(ctx, ideas[0].id)
    v2 = r.approve(ctx, ideas[0].id)
    assert v1.id == v2.id and v1.stage == "approved" and ctx.session.query(Video).count() == 1
    assert ctx.session.get(Idea, ideas[0].id).status == "approved"
