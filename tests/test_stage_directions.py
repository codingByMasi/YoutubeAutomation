"""Stage directions describe on-screen action only: never spoken, never captioned."""
from studio.story import narration as nar


def test_stage_directions_are_not_spoken():
    text = ("The loan was paid off in 2015. She states it plainly. No jokes here. He puts down the pen. "
            "Nobody speaks for a moment. Then he closes the ledger. The debt was real.")
    assert nar.spoken(text) == "The loan was paid off in 2015. The debt was real."


def test_pronoun_whistle_direction_removed():
    assert nar.spoken("She whistles. Slow down, Dash. We need that page.") == "Slow down, Dash. We need that page."


def test_plain_history_is_untouched():
    text = "Clive marched on Plassey in 1757. The Company won the battle."
    assert nar.spoken(text) == text


def test_all_direction_text_is_kept_not_emptied():
    assert nar.spoken("She states it plainly.") == "She states it plainly."
