"""Canonical call-outcome vocabulary and Plivo CallStatus mapping."""

TERMINAL = frozenset({"Interested", "Not_Interested"})
CALLBACK = frozenset({"Callback_Requested", "Early_Disconnect"})
RETRY = frozenset({"Busy", "No_Answer", "Rejected", "Carrier_Failed",
                   "Wrong_Requirement", "Unknown"})
FAILURE = frozenset({"Max_Attempts_Reached", "Campaign_Cancelled"})

_PLIVO_STATUS_TO_OUTCOME = {
    "busy": "Busy",
    "no-answer": "No_Answer",
    "cancel": "No_Answer",
    "reject": "Rejected",
    "failed": "Carrier_Failed",
}

def outcome_from_plivo_status(call_status: str) -> str:
    """Map Plivo call status to normalized outcome string."""
    return _PLIVO_STATUS_TO_OUTCOME.get((call_status or "").strip().lower(), "Unknown")
