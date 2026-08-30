"""Canonical call-outcome vocabulary and Plivo CallStatus mapping."""

TERMINAL = frozenset({"Interested", "Not_Interested", "Transferred"})
CALLBACK = frozenset({"Callback_Requested", "Early_Disconnect"})
RETRY = frozenset({"Busy", "No_Answer", "Rejected", "Carrier_Failed",
                   "Wrong_Requirement", "Unknown"})
FAILURE = frozenset({"Max_Attempts_Reached", "Campaign_Cancelled"})

# Global vocabulary of "every outcome the backend can produce" — used as a
# fallback when a campaign's own configured outcome set can't be resolved.
# Add a new outcome to one of the sets above and it shows up here automatically.
ALL_OUTCOMES = sorted(TERMINAL | CALLBACK | RETRY | FAILURE)

# Outcomes produced by dialer/telephony/orphan-handling logic rather than a
# script's own LLM intent extraction. These are never part of a
# script_configs row's outcome_terminal/outcome_retry/outcome_callback lists,
# so no script config's customization can turn them off — they can happen to
# any campaign regardless of which script it runs. GET /api/campaigns/{id}/outcomes
# unions these into whatever that campaign's script contributes.
SYSTEM_OUTCOMES = frozenset({
    "No_Answer",             # Plivo CallStatus "no-answer" / "cancel"
    "Rejected",              # Plivo CallStatus "reject"
    "Carrier_Failed",        # Plivo CallStatus "failed"
    "Max_Attempts_Reached",  # dialer: attempts exhausted
    "Campaign_Cancelled",    # dialer: campaign cancelled mid-run
    "Transferred",           # cascade cold transfer to a human
})

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


# Display order for outcome dropdowns: the two "reached a real answer" terminal
# outcomes lead, the rest follow alphabetically. Anything not explicitly
# prioritized keeps its normal sort position.
_PRIORITY_ORDER = ("Interested", "Not_Interested")


def order_outcomes(outcomes) -> list[str]:
    """Sort outcomes with Interested/Not_Interested pinned to the top."""
    rest = sorted(o for o in outcomes if o not in _PRIORITY_ORDER)
    priority = [o for o in _PRIORITY_ORDER if o in outcomes]
    return priority + rest
