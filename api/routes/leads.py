"""Client /api/campaigns/{campaign_id}/leads CRUD routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from io import BytesIO

from fastapi.responses import StreamingResponse

from openpyxl import Workbook
from openpyxl.styles import Font

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import client_id_uuid, get_client_from_token, get_pool
from api.guards import require_campaign_modifiable, require_lead_editable
from api.routes.campaigns import _get_lead_schema
from compliance import is_call_allowed, next_compliant_time
from db import postgres as pg_db
from lead_upload.normaliser import normalise_phone
from lead_upload.validator import extract_lead_fields, field_display_header

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


def _parse_metadata(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}



def _build_export_layout(lead_schema: dict, rows: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Build schema-driven columns + system columns for export.

    Order: Name, Phone, Lead Schema fields, then system columns.
    Lead Schema is the single source of truth — no ad-hoc metadata extras.
    """
    import_cols: list[dict] = []
    seen: set[str] = set()

    for label, key in [("Name", "name"), ("Phone", "phone")]:
        import_cols.append({"header": label, "kind": "field", "key": key})
        seen.add(label.lower())

    for field in extract_lead_fields(lead_schema):
        key = field.get("key")
        if not key:
            continue
        if str(key).strip().lower() in ("phone", "name", "lead_phone", "lead_name", "lead_type"):
            continue
        header = field_display_header(field)
        ncol = header.strip().lower()
        if ncol in ("phone", "name", "lead_phone", "lead_name", "lead_type"):
            continue
        header_key = header.lower()
        if header_key not in seen:
            alt = []
            for cand in (field.get("csv_column"), field.get("label"), field.get("key"), key):
                if cand and str(cand).strip() and str(cand).strip().lower() not in {a.lower() for a in alt}:
                    alt.append(str(cand).strip())
            import_cols.append({"header": header, "kind": "metadata", "key": key, "alt_keys": alt})
            seen.add(header_key)

    system_cols = [
        ("Status", "status"),
        ("Outcome", "outcome"),
        ("Attempts", "attempts"),
        ("Turns", "transcript_turns"),
        ("Interested", "_interested"),
        ("Last Call Duration", "last_call_duration_seconds"),
        ("Last Call", "last_call_ended_at"),
        ("Created Time", "created_at"),
        ("Updated Time", "updated_at"),
    ]
    return import_cols, system_cols

def _import_cell(row: dict, spec: dict) -> str:
    if spec["kind"] == "field":
        if spec["key"] == "phone":
            return str(row.get("phone") or "")
        return str(row.get("name") or "")
    meta = _parse_metadata(row.get("metadata"))
    for candidate in [spec.get("key"), *(spec.get("alt_keys") or []), spec.get("header")]:
        if candidate is None:
            continue
        if candidate in meta and meta[candidate] is not None:
            return str(meta[candidate])
        # case-insensitive fallback
        lower = str(candidate).lower()
        for mk, mv in meta.items():
            if str(mk).lower() == lower and mv is not None:
                return str(mv)
    return ""


def _system_cell(row: dict, field: str):
    if field == "_interested":
        return "Yes" if (row.get("outcome") or "").strip() == "Interested" else "No"
    val = row.get(field)
    return "" if val is None else val


# ── Feature 0: Read leads ───────────────────────────────────────────────────

@router.get("/{campaign_id}/leads")
async def list_leads(
    campaign_id: UUID,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
    outcome: str | None = None,
    turns: str | None = None,
    attempts: str | None = None,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Get a paginated list of leads for a campaign.

    Filter query params accept a single value or comma-separated values.
    Within a filter category values are OR'd; across categories they are AND'd.
    """
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
        outcome=outcome,
        turns=turns,
        attempts=attempts,
    )
    return {
        "leads": leads,
        "limit": limit,
        "offset": offset,
        "status": status,
        "search": search,
        "outcome": outcome,
        "turns": turns,
        "attempts": attempts,
        "total_count": total_count,
    }


@router.get("/{campaign_id}/leads/export")
async def export_leads(
    campaign_id: UUID,
    status: str | None = None,
    search: str | None = None,
    outcome: str | None = None,
    turns: str | None = None,
    attempts: str | None = None,
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Export campaign leads as Excel (.xlsx)."""

    cid = client_id_uuid(client)
    camp = await _get_campaign_or_404(pool, campaign_id, cid)

    rows = await pg_db.list_campaign_leads_for_export(
        pool,
        campaign_id,
        cid,
        status=status,
        search=search,
        outcome=outcome,
        turns=turns,
        attempts=attempts,
    )

    bot = await pg_db.get_bot_config(
        pool, UUID(str(camp["bot_config_id"])), cid
    )
    lead_schema = (
        await _get_lead_schema(pool, bot, cid)
        if bot is not None
        else {"fields": []}
    )
    import_cols, system_cols = _build_export_layout(lead_schema, rows)
    headers = [c["header"] for c in import_cols] + [label for label, _ in system_cols]

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        values = [_import_cell(row, spec) for spec in import_cols]
        values.extend(_system_cell(row, field) for _, field in system_cols)
        ws.append(values)

    phone_col_idx = next(
        (i + 1 for i, spec in enumerate(import_cols) if spec.get("key") == "phone"),
        None,
    )
    if phone_col_idx:
        col_letter = ws.cell(row=1, column=phone_col_idx).column_letter
        for cell in ws[col_letter]:
            cell.number_format = "@"

    slug = (camp.get("name") or "campaign").replace(" ", "_")[:40]

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}_leads.xlsx"'
        },
    )


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


