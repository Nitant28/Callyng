"""Tests for the pre-save turn-count validation on the 'Interested' outcome."""

from __future__ import annotations

from post_call_processor import count_transcript_turns, validate_interested_outcome


def _turn(role: str, content: str = "hi") -> dict:
    return {"role": role, "content": content}


def test_count_transcript_turns_splits_by_role():
    transcript = [
        _turn("assistant"),
        _turn("user"),
        _turn("assistant"),
        _turn("system"),  # ignored, not assistant/user
    ]
    assistant_turns, user_turns = count_transcript_turns(transcript)
    assert assistant_turns == 2
    assert user_turns == 1


def test_interested_downgraded_when_five_or_fewer_turns():
    # total_turns == 5 -> not > 5 -> downgrade
    transcript = [
        _turn("assistant"),
        _turn("user"),
        _turn("assistant"),
        _turn("user"),
        _turn("assistant"),
    ]
    assert validate_interested_outcome("Interested", transcript) == "Unknown"


def test_interested_kept_when_more_than_five_turns():
    transcript = [_turn("assistant"), _turn("user")] * 3  # 6 turns
    assert validate_interested_outcome("Interested", transcript) == "Interested"


def test_interested_downgraded_with_no_transcript():
    assert validate_interested_outcome("Interested", []) == "Unknown"
    assert validate_interested_outcome("Interested", None) == "Unknown"


def test_non_interested_outcomes_are_never_touched():
    short_transcript = [_turn("assistant")]
    for outcome in (
        "Not_Interested",
        "Busy",
        "Callback_Requested",
        "Unknown",
        "Early_Disconnect",
        "Wrong_Requirement",
    ):
        assert validate_interested_outcome(outcome, short_transcript) == outcome


def test_case_insensitive_match_on_interested():
    transcript = [_turn("assistant")]  # 1 turn, would fail threshold
    assert validate_interested_outcome("interested", transcript) == "Unknown"
    assert validate_interested_outcome("INTERESTED", transcript) == "Unknown"
