"""Unit tests for canonical outcome vocabulary and Plivo mapping."""

from call_outcomes import outcome_from_plivo_status


def test_outcome_from_plivo_status_busy():
    assert outcome_from_plivo_status("busy") == "Busy"


def test_outcome_from_plivo_status_no_answer():
    assert outcome_from_plivo_status("no-answer") == "No_Answer"
    assert outcome_from_plivo_status("cancel") == "No_Answer"


def test_outcome_from_plivo_status_reject():
    assert outcome_from_plivo_status("reject") == "Rejected"


def test_outcome_from_plivo_status_carrier_failed():
    assert outcome_from_plivo_status("failed") == "Carrier_Failed"


def test_outcome_from_plivo_status_unknown():
    assert outcome_from_plivo_status("") == "Unknown"
    assert outcome_from_plivo_status("completed") == "Unknown"
