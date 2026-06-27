"""Client /api/campaigns/{campaign_id}/leads CRUD routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import client_id_uuid, get_client_from_token, get_pool
from api.guards import require_campaign_modifiable, require_lead_editable
from compliance import is_call_allowed, next_compliant_time
from db import postgres as pg_db
from lead_upload.normaliser import normalise_phone

router = APIRouter(prefix="/api/campaigns", tags=["leads"])

# ── Allowed manual status transitions ────────────────────────────────────────

_MANUAL_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"failed", "callback_scheduled", "completed"},
    "callback_scheduled": {"pending", "failed", "completed"},
    "failed": {"pending", "completed"},
    "completed": {"pending"},
}


# ── Request bodies ───────────────────────────────────────────────────────────

class EditLeadBody(BaseModel):
    name: str | None = None
    lead_type: str | None = None
    metadata: dict | None = None


class AddLeadBody(BaseModel):
    phone: str
    name: str | None = None
    lead_type: str | None = Field(default="cold")
    metadata: dict | None = None


class ChangeStatusBody(BaseModel):
    status: str
    scheduled_at: datetime | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_campaign_or_404(pool, campaign_id: UUID, cid: UUID) -> dict:
    camp = await pg_db.get_campaign(pool, campaign_id, cid)
    if camp is None:
        raise HTTPException(404, "Campaign not found")
    return camp


async def _get_lead_or_404(pool, lead_id: UUID, cid: UUID, campaign_id: UUID) -> dict:
    lead = await pg_db.get_lead(pool, lead_id, cid)
    if lead is None:
        raise HTTPException(404, "Lead not found")
    if str(lead.get("campaign_id")) != str(campaign_id):
        raise HTTPException(404, "Lead does not belong to this campaign")
    return lead


# ── Feature 0: Read leads ───────────────────────────────────────────────────

@router.get("/{campaign_id}/leads")
async def list_leads(
    campaign_id: UUID,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Get a paginated list of leads for a campaign."""
    cid = client_id_uuid(client)
    await _get_campaign_or_404(pool, campaign_id, cid)

    leads, total_count = await pg_db.list_campaign_leads(
        pool,
        campaign_id,
        cid,
        limit=limit,
        offset=offset,
        status=status,
        search=search,
    )
    return {"leads": leads, "limit": limit, "offset": offset, "status": status, "search": search, "total_count": total_count}


@router.get("/{campaign_id}/leads/{lead_id}")
async def get_lead(
    campaign_id: UUID,
    lead_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Get details for a single lead."""
    cid = client_id_uuid(client)
    await _get_campaign_or_404(pool, campaign_id, cid)
    lead = await _get_lead_or_404(pool, lead_id, cid, campaign_id)
    return {"lead": lead}


# ── Feature 1: Edit lead fields ─────────────────────────────────────────────

@router.patch("/{campaign_id}/leads/{lead_id}")
async def edit_lead(
    campaign_id: UUID,
    lead_id: UUID,
    body: EditLeadBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Update user-editable fields (name, lead_type, metadata) on a lead."""
    cid = client_id_uuid(client)
    camp = await _get_campaign_or_404(pool, campaign_id, cid)

    # Block on running / completed / cancelled
    require_campaign_modifiable(camp)

    lead = await _get_lead_or_404(pool, lead_id, cid, campaign_id)
    require_lead_editable(lead)

    if body.lead_type is not None and body.lead_type not in ("cold", "warm", "hot"):
        raise HTTPException(422, "lead_type must be one of: cold, warm, hot")

    if body.name is None and body.lead_type is None and body.metadata is None:
        raise HTTPException(400, "No fields to update")

    updated = await pg_db.update_lead_fields(
        pool,
        lead_id,
        cid,
        name=body.name,
        lead_type=body.lead_type,
        metadata=body.metadata,
    )
    if not updated:
        raise HTTPException(404, "Lead not found")

    refreshed = await pg_db.get_lead(pool, lead_id, cid)
    return {"lead": refreshed}


# ── Feature 2: Add a single lead ────────────────────────────────────────────

@router.post("/{campaign_id}/leads")
async def add_lead(
    campaign_id: UUID,
    body: AddLeadBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Add a single lead to a campaign (same validations as CSV upload)."""
    cid = client_id_uuid(client)
    camp = await _get_campaign_or_404(pool, campaign_id, cid)

    # Only draft or paused
    require_campaign_modifiable(camp)

    # Phone normalisation
    phone = normalise_phone(body.phone)
    if not phone:
        raise HTTPException(422, f"Invalid phone number: {body.phone}")

    status = "pending"
    allowed, reason = is_call_allowed()
    next_attempt_at = None
    if not allowed and "window" in reason:
        next_attempt_at = next_compliant_time()

    if body.lead_type and body.lead_type not in ("cold", "warm", "hot"):
        raise HTTPException(422, "lead_type must be one of: cold, warm, hot")

    lead_dict = {
        "client_id": cid,
        "campaign_id": campaign_id,
        "phone": phone,
        "name": body.name,
        "lead_type": body.lead_type or "cold",
        "status": status,
        "max_attempts": int(camp.get("max_attempts") or 3),
        "next_attempt_at": next_attempt_at,
        "metadata": body.metadata or {},
    }

    try:
        inserted = await pg_db.insert_single_lead(pool, lead_dict)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return {
        "lead": inserted,
    }


# ── Feature 3: Delete a lead ────────────────────────────────────────────────

@router.delete("/{campaign_id}/leads/{lead_id}")
async def delete_lead(
    campaign_id: UUID,
    lead_id: UUID,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Hard-delete a lead. call_logs are preserved."""
    cid = client_id_uuid(client)
    camp = await _get_campaign_or_404(pool, campaign_id, cid)

    # Only draft or paused
    require_campaign_modifiable(camp)

    lead = await _get_lead_or_404(pool, lead_id, cid, campaign_id)
    require_lead_editable(lead)

    deleted = await pg_db.delete_lead(pool, lead_id, campaign_id, cid)
    if not deleted:
        raise HTTPException(404, "Lead not found")

    # Full counter reconcile after delete
    counters = await pg_db.reconcile_campaign_counters(pool, campaign_id, cid)

    return {
        "deleted": True,
        "lead_id": str(lead_id),
        "counters": counters,
    }


# ── Feature 4: Manual status change ─────────────────────────────────────────

@router.patch("/{campaign_id}/leads/{lead_id}/status")
async def change_lead_status(
    campaign_id: UUID,
    lead_id: UUID,
    body: ChangeStatusBody,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Manually change a lead's status (enforced transition table)."""
    cid = client_id_uuid(client)
    camp = await _get_campaign_or_404(pool, campaign_id, cid)

    # Block on running / completed / cancelled
    require_campaign_modifiable(camp)

    lead = await _get_lead_or_404(pool, lead_id, cid, campaign_id)
    require_lead_editable(lead)

    current = lead["status"]
    target = body.status

    # calling is never a valid manual target
    if target == "calling":
        raise HTTPException(409, "Cannot manually set status to 'calling' — dialer-only transition")

    allowed_targets = _MANUAL_TRANSITIONS.get(current)
    if allowed_targets is None:
        raise HTTPException(
            409,
            f"Cannot change status from '{current}' — lead is in a non-editable state",
        )
    if target not in allowed_targets:
        raise HTTPException(
            409,
            f"Transition '{current}' → '{target}' is not allowed. "
            f"Allowed targets: {', '.join(sorted(allowed_targets))}",
        )

    attempts = int(lead.get("attempts") or 0)
    max_attempts = int(lead.get("max_attempts") or 3)
    
    if target == "callback_scheduled" and attempts >= max_attempts:
        raise HTTPException(
            409,
            "Cannot schedule a callback for a lead that has reached its maximum attempts. "
            "Please move it to 'Pending' first to reset its attempt counter."
        )

    # Compute next_attempt_at and scheduled_callback_at based on target
    next_attempt_at: datetime | None = None
    scheduled_callback_at: datetime | None = None

    if target == "callback_scheduled":
        scheduled_at = body.scheduled_at or (datetime.now(timezone.utc) + timedelta(hours=4))
        next_attempt_at = scheduled_at
        scheduled_callback_at = scheduled_at
    elif target == "pending":
        next_attempt_at = datetime.now(timezone.utc)

    updated = await pg_db.update_lead_status_manual(
        pool,
        lead_id,
        cid,
        target,
        next_attempt_at=next_attempt_at,
        scheduled_callback_at=scheduled_callback_at,
        reset_to_fresh=(target == "pending"),
    )
    if not updated:
        raise HTTPException(404, "Lead not found")

    # Full counter reconcile after manual status change
    counters = await pg_db.reconcile_campaign_counters(pool, campaign_id, cid)

    refreshed = await pg_db.get_lead(pool, lead_id, cid)
    return {
        "lead": refreshed,
        "transition": f"{current} → {target}",
        "counters": counters,
    }


