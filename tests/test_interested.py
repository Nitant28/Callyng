"""Exact interested matching — 'not interested' must never send."""

from followups.interested import is_interested_outcome, is_negative_intent
from n8n_webhook import outcome_to_event


def test_positive_interest_labels_send():
    for label in ("Interested", "interested", "INTERESTED", "hot", "WARM", "qualified"):
        assert is_interested_outcome(label) is True
        assert outcome_to_event(label) == "lead_qualified"


def test_negative_interest_labels_never_send():
    for label in (
        "Not Interested",
        "not interested",
        "NOT_INTERESTED",
        "not-interested",
        "uninterested",
        "disinterested",
    ):
        assert is_interested_outcome(label) is False
        assert is_negative_intent(label) is True
        assert outcome_to_event(label) == "lead_not_interested"


def test_neutral_and_missing_do_not_qualify():
    for label in ("", None, "neutral", "maybe", "unknown", "very interested"):
        assert is_interested_outcome(label) is False
    assert outcome_to_event("Busy") == "lead_failed"
    assert outcome_to_event("maybe") is None
    assert outcome_to_event("very interested") is None
    assert outcome_to_event("") is None
