"""Integration-style tests for early disconnect post-call routing."""

from __future__ import annotations

from datetime import datetime, timezone

from post_call_processor import (
    _lead_transition,
    apply_early_disconnect_policy,
    resolve_post_call_transition,
)


def test_callee_hangup_unknown_routes_to_callback_scheduled():
    new_status, next_at, sched_cb, fire_webhook = resolve_post_call_transition(
        "calling",
        "Unknown",
        1,
        3,
        120,
        {},
        lead_next_attempt_at=None,
        lead_scheduled_callback_at=None,
        callee_hangup=True,
    )
    assert new_status == "callback_scheduled"
    assert next_at is not None
    assert sched_cb == next_at
    assert fire_webhook is False


def test_early_disconnect_uses_retry_delay_not_four_hours():
    status, next_at, sched_cb, fire = _lead_transition(
        "Early_Disconnect",
        attempts=1,
        max_attempts=3,
        retry_delay_minutes=10,
        extraction={},
    )
    assert status == "callback_scheduled"
    assert next_at is not None
    assert sched_cb == next_at
    assert fire is True
    assert (next_at - datetime.now(timezone.utc)).total_seconds() < 660


def test_policy_then_transition_early_disconnect():
    outcome = apply_early_disconnect_policy(
        intent_status="Unknown",
        duration_seconds=12,
        callee_hangup=True,
    )
    assert outcome == "Early_Disconnect"
    status, next_at, sched_cb, _ = _lead_transition(
        outcome,
        attempts=1,
        max_attempts=3,
        retry_delay_minutes=30,
        extraction={},
    )
    assert status == "callback_scheduled"
    assert next_at is not None
    assert sched_cb == next_at
