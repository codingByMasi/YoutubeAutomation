import json

import pytest
from typer.testing import CliRunner

from studio.cli import app
from studio.config import load_settings
from studio.errors import StudioError
from studio.growth import channels, profile, store
from studio.stages.script import build_prompt


def test_default_channel_and_legacy_migration(root):
    store.save(store.channel_file(root, "profile"), {"name": "Old Name", "posts_per_week": 5})
    rows = channels.list_channels(root)
    assert [r["id"] for r in rows] == ["default"] and rows[0]["active"]
    assert profile.load(root)["name"] == "Old Name" and profile.load(root)["language"] == "English"


def test_add_edit_switch_remove(root):
    cid = channels.add(root, "Money Maps", niche="Personal finance", posts_per_week=3, voice="en-US-JennyNeural")
    assert cid == "money-maps" and channels.active_id(root) == cid
    assert profile.load(root)["niche"] == "Personal finance"
    assert channels.add(root, "Money Maps", activate=False) == "money-maps-2"
    channels.update(root, "money-maps-2", description="Second one", bogus=1)
    assert channels.get(root, "money-maps-2")["description"] == "Second one"
    channels.switch(root, "default")
    assert profile.save(root, {"name": "Mine"})["name"] == "Mine"
    channels.remove(root, "default")
    assert channels.active_id(root) == "money-maps"
    with pytest.raises(StudioError):
        channels.switch(root, "nope")
    channels.remove(root, "money-maps-2")
    with pytest.raises(StudioError):
        channels.remove(root, "money-maps")


def test_active_channel_drives_voice_and_prompt(root):
    assert load_settings(root).tts_voice == "en-US-AndrewNeural"
    assert "economics" in build_prompt(root, "t").lower()
    channels.add(root, "Chef Talk", niche="Cooking science", description="Why recipes work",
                 voice="en-GB-RyanNeural", youtube_channel_id="UC123")
    s = load_settings(root)
    assert s.tts_voice == "en-GB-RyanNeural" and s.channel_id == "UC123"
    prompt = build_prompt(root, "Why bread rises")
    assert "Cooking science" in prompt and "Why recipes work" in prompt
    channels.switch(root, "default")
    assert load_settings(root).tts_voice == "en-US-AndrewNeural"


def test_export_import_roundtrip(root, tmp_path):
    channels.add(root, "A", niche="Alpha")
    text = channels.export_json(root)
    other = tmp_path / "other"
    other.mkdir()
    assert channels.import_json(other, text) == ["a"]  # "default" already exists there
    assert channels.get(other, "a")["niche"] == "Alpha"
    assert channels.import_json(other, text) == []  # existing ids kept
    with pytest.raises(StudioError):
        channels.import_json(other, "not json")
    with pytest.raises(StudioError):
        channels.import_json(other, json.dumps({"hello": 1}))


def test_cli_channels(root, monkeypatch):
    monkeypatch.setenv("STUDIO_HOME", str(root))
    r = CliRunner()
    assert r.invoke(app, ["channels", "add", "Tech Bits", "--niche", "Gadgets", "--posts-per-week", "4"]).exit_code == 0
    out = r.invoke(app, ["channels", "list"]).output
    assert "* tech-bits" in out and "Gadgets" in out and "4/week" in out
    assert r.invoke(app, ["channels", "use", "default"]).exit_code == 0
    assert r.invoke(app, ["channels", "edit", "tech-bits", "--voice", "en-US-AriaNeural"]).exit_code == 0
    assert channels.get(root, "tech-bits")["voice"] == "en-US-AriaNeural"
    f = root / "out.json"
    assert r.invoke(app, ["channels", "export", str(f)]).exit_code == 0
    assert r.invoke(app, ["channels", "remove", "tech-bits"]).exit_code == 0
    assert "tech-bits" in r.invoke(app, ["channels", "import", str(f)]).output


def test_data_is_separated_per_channel(make_ctx, root):
    from studio.context import build_ctx
    from studio.growth import series as series_mod
    from studio.web import service as svc

    a = build_ctx(root)
    svc.add_manual_topic(a, "topic for default")
    series_mod.create(root, "Default series", "", ["x"])
    channels.add(root, "Other", niche="Gardening")
    b = build_ctx(root)  # new context follows the newly active channel
    assert b.session.info["channel_id"] == "other"
    assert svc.ideas_for(b) == [] and svc.list_videos(b) == []
    assert series_mod.load(root) == []
    svc.add_manual_topic(b, "grow tomatoes")
    series_mod.create(root, "Garden series", "", ["y"])
    assert [i.topic for i in svc.ideas_for(b)] == ["grow tomatoes"]
    channels.switch(root, "default")
    a2 = build_ctx(root)
    assert [i.topic for i in svc.ideas_for(a2)] == ["topic for default"]
    assert [s["name"] for s in series_mod.load(root)] == ["Default series"]


def test_old_database_gets_channel_column(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from studio.db import init_db
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE ideas (id INTEGER PRIMARY KEY, seed VARCHAR(200), topic VARCHAR(300), "
                       "demand_score FLOAT, competition_score FLOAT, outlier_score FLOAT, status VARCHAR(20), "
                       "created_at DATETIME)"))
        c.execute(text("INSERT INTO ideas (seed, topic) VALUES ('s', 't')"))
    init_db(eng)
    assert "channel_id" in {c["name"] for c in inspect(eng).get_columns("ideas")}
    with eng.connect() as c:
        assert c.execute(text("SELECT channel_id FROM ideas")).scalar() == "default"


def test_custom_niche_relaxes_topic_filter(root):
    from studio.stages.discover import clean_topics, fits_channel
    assert not fits_channel("best tomato varieties")
    assert clean_topics(["best tomato varieties"], "gardening", strict=False) == ["best tomato varieties"]
    assert not fits_channel("tomato game cheats", strict=False)
