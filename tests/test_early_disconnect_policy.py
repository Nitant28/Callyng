"""Unit tests for apply_early_disconnect_policy."""

from __future__ import annotations

from post_call_processor import (
    EARLY_DISCONNECT_MAX_SECONDS,
    apply_early_disconnect_policy,
)


def test_early_disconnect_short_callee_unknown():
    assert (
        apply_early_disconnect_policy(
            intent_status="Unknown",
            duration_seconds=8,
            callee_hangup=True,
        )
        == "Early_Disconnect"
    )


def test_early_disconnect_short_callee_empty_intent():
    assert (
        apply_early_disconnect_policy(
            intent_status="",
            duration_seconds=5,
            callee_hangup=True,
        )
        == "Early_Disconnect"
    )


def test_early_disconnect_not_callee_hangup():
    assert (
        apply_early_disconnect_policy(
            intent_status="Unknown",
            duration_seconds=5,
            callee_hangup=False,
        )
        is None
    )


def test_early_disconnect_at_threshold():
    assert (
        apply_early_disconnect_policy(
            intent_status="Unknown",
            duration_seconds=EARLY_DISCONNECT_MAX_SECONDS,
            callee_hangup=True,
        )
        is None
    )


def test_early_disconnect_transferred_not_rewritten():
    assert (
        apply_early_disconnect_policy(
            intent_status="Transferred",
            duration_seconds=5,
            callee_hangup=True,
        )
        is None
    )


def test_early_disconnect_strong_intent_not_applied():
    assert (
        apply_early_disconnect_policy(
            intent_status="Interested",
            duration_seconds=5,
            callee_hangup=True,
        )
        is None
    )
