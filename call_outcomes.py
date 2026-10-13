"""Canonical call-outcome vocabulary and Telephony (Telnyx) CallStatus mapping."""

TERMINAL = frozenset({"Interested", "Not_Interested", "Transferred"})
CALLBACK = frozenset({"Callback_Requested", "Early_Disconnect"})
RETRY = frozenset({"Busy", "No_Answer", "Rejected", "Carrier_Failed",
                   "Wrong_Requirement", "Unknown"})
FAILURE = frozenset({"Max_Attempts_Reached", "Campaign_Cancelled"})

ALL_OUTCOMES = sorted(TERMINAL | CALLBACK | RETRY | FAILURE)

SYSTEM_OUTCOMES = frozenset({
    "No_Answer",             # Telephony status "no-answer" / "cancel" / "timeout"
    "Rejected",              # Telephony status "reject" / "call_rejected"
    "Carrier_Failed",        # Telephony status "failed" / "carrier_failed"
    "Max_Attempts_Reached",  # dialer: attempts exhausted
    "Campaign_Cancelled",    # dialer: campaign cancelled mid-run
    "Transferred",           # cascade cold transfer to a human
})

_TELEPHONY_STATUS_TO_OUTCOME = {
    # Telnyx & standard telephony hangup causes / statuses
    "busy": "Busy",
    "user_busy": "Busy",
    "no-answer": "No_Answer",
    "no_answer": "No_Answer",
    "timeout": "No_Answer",
    "cancel": "No_Answer",
    "originator_cancel": "No_Answer",
    "reject": "Rejected",
    "rejected": "Rejected",
    "call_rejected": "Rejected",
    "failed": "Carrier_Failed",
    "carrier_failed": "Carrier_Failed",
    "subscriber_absent": "No_Answer",
    "unallocated_number": "Carrier_Failed",
    "destination_out_of_order": "Carrier_Failed",
}


def outcome_from_telephony_status(call_status: str) -> str:
    """Map Telephony (Telnyx) call status / hangup cause to normalized outcome string."""
    key = (call_status or "").strip().lower().replace(" ", "_")
    return _TELEPHONY_STATUS_TO_OUTCOME.get(key, "Unknown")


# Compatibility alias
outcome_from_plivo_status = outcome_from_telephony_status


_PRIORITY_ORDER = ("Interested", "Not_Interested")


def order_outcomes(outcomes) -> list[str]:
    """Sort outcomes with Interested/Not_Interested pinned to the top."""
    rest = sorted(o for o in outcomes if o not in _PRIORITY_ORDER)
    priority = [o for o in _PRIORITY_ORDER if o in outcomes]
    return priority + rest
