"""Narration styles: per-type defaults, per-channel choice, prompt text and narrator voice."""
import pytest

from studio.errors import StudioError
from studio.growth import channels
from studio.story import narration_styles as ns
from studio.story import profile, prompts


def test_defaults_per_type():
    assert profile.get("history")["narration"] == "comic_storyteller"
    assert profile.get("explainer")["narration"] == "calm_explainer"
    assert profile.get("kids")["narration"] == "warm_singsong"
    assert profile.get("history")["narration_voice"]["kokoro"] == "am_adam"


def test_choice_overrides_default_and_story_wps_still_wins():
    assert profile.get("history", None, "hushed_suspense")["narration"] == "hushed_suspense"
    assert profile.get("history", {"wps": 2.2})["wps"] == 2.2


def test_bad_style_names_the_fix():
    with pytest.raises(StudioError) as e:
        ns.check("jazz")
    assert "comic_storyteller" in str(e.value)


def test_channel_field_saved_and_validated(tmp_path):
    cid = channels.add(tmp_path, "H", type="history", narration="dramatic_documentary")
    assert channels.get(tmp_path, cid)["narration"] == "dramatic_documentary"
    assert profile.for_channel(tmp_path)["narration"] == "dramatic_documentary"
    with pytest.raises(StudioError):
        channels.update(tmp_path, cid, narration="nope")


def test_history_prompt_has_comic_rules_and_no_sources():
    prof = profile.get("history")
    text = prompts.compose("script", prof, topic="Hannibal", brief="b", style="s", outline="o")
    assert "Comic storyteller" in text and "speech" in text
    assert not prompts.asks_for_sources(text)
    assert "Calm explainer" in prompts.compose("script", profile.get("explainer"), topic="t", brief="b", style="s",
                                               outline="o")
