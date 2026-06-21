"""Reusable guard checks for campaign / lead API endpoints."""

from __future__ import annotations

from fastapi import HTTPException


def require_campaign_modifiable(
    camp: dict,
    *,
    allow_paused: bool = True,
) -> None:
    """Raise 409 if campaign status doesn't allow lead modifications.

    Parameters
    ----------
    camp:
        Campaign dict from ``get_campaign``.
    allow_paused:
        When *True* (default), both ``draft`` and ``paused`` are permitted.
        Set *False* to allow only ``draft``.
    """
    allowed = {"draft", "paused"} if allow_paused else {"draft"}
    if camp["status"] not in allowed:
        raise HTTPException(
            409,
            f"Cannot modify leads while campaign is {camp['status']}",
        )


def require_lead_editable(lead: dict) -> None:
    """Raise 409 if the lead is currently on a live call."""
    if lead.get("status") == "calling":
        raise HTTPException(
            409,
            "Lead is currently on a live call and cannot be modified",
        )
