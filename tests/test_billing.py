"""Pure unit tests for per-second billing (no DATABASE_URL)."""

from decimal import Decimal

from billing import (
    BILLING_RESERVE_MINUTES,
    compute_call_charge,
    reservation_credits,
)


def test_reserve_minutes_constant():
    assert BILLING_RESERVE_MINUTES == 2


def test_fifteen_seconds_at_3_50():
    result = compute_call_charge(15, Decimal("3.50"), Decimal("0.60"))
    assert result["billed_minutes"] == Decimal("0.2500")
    assert result["started_minutes"] == Decimal("1")
    assert result["setup_charge"] == Decimal("0.6000")
    assert result["duration_charge"] == Decimal("0.8750")
    assert result["credits_charged"] == Decimal("1.4750")
    assert result["budget_amount"] == Decimal("1.48")


def test_forty_five_seconds_at_4_00():
    result = compute_call_charge(45, Decimal("4.00"), Decimal("0.60"))
    assert result["billed_minutes"] == Decimal("0.7500")
    assert result["started_minutes"] == Decimal("1")
    assert result["setup_charge"] == Decimal("0.6000")
    assert result["duration_charge"] == Decimal("3.0000")
    assert result["credits_charged"] == Decimal("3.6000")
    assert result["budget_amount"] == Decimal("3.60")


def test_fifty_nine_seconds_at_3_50():
    result = compute_call_charge(59, Decimal("3.50"), Decimal("0.60"))
    assert result["started_minutes"] == Decimal("1")
    assert result["setup_charge"] == Decimal("0.6000")
    assert result["duration_charge"] == Decimal("3.4417")
    assert result["credits_charged"] == Decimal("4.0417")
    assert result["budget_amount"] == Decimal("4.04")


def test_sixty_five_seconds_crosses_second_started_minute():
    result = compute_call_charge(65, Decimal("3.50"), Decimal("0.60"))
    assert result["started_minutes"] == Decimal("2")
    assert result["setup_charge"] == Decimal("1.2000")
    assert result["duration_charge"] == Decimal("3.7917")
    assert result["credits_charged"] == Decimal("4.9917")
    assert result["budget_amount"] == Decimal("4.99")


def test_one_twenty_five_seconds_crosses_third_started_minute():
    result = compute_call_charge(125, Decimal("3.50"), Decimal("0.60"))
    assert result["started_minutes"] == Decimal("3")
    assert result["setup_charge"] == Decimal("1.8000")
    assert result["duration_charge"] == Decimal("7.2917")
    assert result["credits_charged"] == Decimal("9.0917")
    assert result["budget_amount"] == Decimal("9.09")


def test_ninety_seconds_custom_setup():
    result = compute_call_charge(90, Decimal("6.00"), Decimal("0.50"))
    assert result["billed_minutes"] == Decimal("1.5000")
    assert result["started_minutes"] == Decimal("2")
    assert result["setup_charge"] == Decimal("1.0000")
    assert result["duration_charge"] == Decimal("9.0000")
    assert result["credits_charged"] == Decimal("10.0000")
    assert result["budget_amount"] == Decimal("10.00")


def test_busy_zero_duration_setup_only():
    """Pure formula: 0s still maps to 1 started minute of setup.

    Unanswered dials never call this path for billing — they settle at ₹0.
    """
    result = compute_call_charge(0, Decimal("4.00"), Decimal("0.60"))
    assert result["billed_minutes"] == Decimal("0.0000")
    assert result["started_minutes"] == Decimal("1")
    assert result["setup_charge"] == Decimal("0.6000")
    assert result["duration_charge"] == Decimal("0.0000")
    assert result["credits_charged"] == Decimal("0.6000")
    assert result["budget_amount"] == Decimal("0.60")


def test_zero_rate_and_setup_is_free():
    result = compute_call_charge(90, Decimal("0"), Decimal("0"))
    assert result["credits_charged"] == Decimal("0.0000")
    assert result["budget_amount"] == Decimal("0.00")


def test_reservation_2_50_rate_default_setup():
    assert reservation_credits(Decimal("0.60"), Decimal("2.50")) == Decimal("6.20")


def test_reservation_3_50_rate():
    assert reservation_credits(Decimal("0.60"), Decimal("3.50")) == Decimal("8.20")


def test_accepts_float_and_int_inputs():
    result = compute_call_charge(15, 3.5, 0.6)
    assert result["credits_charged"] == Decimal("1.4750")
    assert result["budget_amount"] == Decimal("1.48")
    assert reservation_credits(0.6, 2.5) == Decimal("6.20")
