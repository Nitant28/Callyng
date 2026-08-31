"""Admin endpoints for remote n8n connectivity tests."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from api.auth import get_pool, require_admin
from followups import repository as followups_repo
from integrations.n8n.config import GLOBAL_WEBHOOK_SETTING, N8nConfig
from integrations.n8n.payload import PAYLOAD_FIELD_SOURCES, build_connectivity_test_payload, build_test_payload
from integrations.n8n.service import N8nService
from integrations.n8n.url_validation import validate_n8n_webhook_url

router = APIRouter(prefix="/internal/n8n", tags=["internal-n8n"])

SETTING_LAST_TEST = "n8n_webhook_last_tested_at"
SETTING_LAST_STATUS = "n8n_webhook_last_test_status"


class N8nTestBody(BaseModel):
    client_id: UUID | None = None
    dry_run: bool = Field(
        default=False,
        description="If true, return the payload without POSTing to n8n.",
    )


class N8nSettingsBody(BaseModel):
    webhook_url: str = Field(
        ...,
        min_length=10,
        max_length=2048,
        validation_alias=AliasChoices("webhook_url", "webhookUrl"),
    )


@router.get("/status")
async def n8n_status(_admin=Depends(require_admin), pool=Depends(get_pool)):
    """Show whether remote n8n webhook is configured (no secrets returned)."""
    cfg = await N8nConfig.resolve(pool)
    env_cfg = N8nConfig.from_env()
    db_url = await followups_repo.get_setting(pool, GLOBAL_WEBHOOK_SETTING)
    last_tested = await followups_repo.get_setting(pool, SETTING_LAST_TEST)
    last_status = await followups_repo.get_setting(pool, SETTING_LAST_STATUS)
    source = cfg.url_source or ("env" if env_cfg.lead_webhook_url else None)
    return {
        "configured": cfg.is_configured,
        "base_url": cfg.base_url or env_cfg.base_url or None,
        "lead_webhook_url_set": bool(cfg.lead_webhook_url),
        "lead_webhook_url_source": "database" if db_url else source,
        "webhook_secret_set": bool(cfg.webhook_secret),
        "timeout_seconds": cfg.timeout_seconds,
        "last_tested_at": last_tested,
        "last_test_status": last_status,
        "webhook_host": (
            cfg.lead_webhook_url.split("/")[2] if cfg.lead_webhook_url and "://" in cfg.lead_webhook_url else None
        ),
    }


@router.get("/settings")
async def n8n_get_settings(_admin=Depends(require_admin), pool=Depends(get_pool)):
    """Return saved webhook URL (full URL for admin — not exposed to client UI)."""
    db_url = await followups_repo.get_setting(pool, GLOBAL_WEBHOOK_SETTING)
    env_cfg = N8nConfig.from_env()
    effective = await N8nConfig.resolve(pool)
    url = db_url or env_cfg.lead_webhook_url or ""
    return {
        "webhook_url": url,
        "configured": effective.is_configured,
        "source": "database" if db_url else ("env" if env_cfg.lead_webhook_url else None),
        "precedence": [
            "client-specific database n8n_lead_webhook_url:{client_id}",
            "global database n8n_lead_webhook_url",
            "N8N_LEAD_WEBHOOK_URL environment variable",
        ],
    }


@router.put("/settings")
async def n8n_save_settings(body: N8nSettingsBody, _admin=Depends(require_admin), pool=Depends(get_pool)):
    url = body.webhook_url.strip().replace("/webhook-test/", "/webhook/")
    ok, err = validate_n8n_webhook_url(url)
    if not ok:
        raise HTTPException(400, err or "Invalid webhook URL")
    await followups_repo.set_setting(pool, GLOBAL_WEBHOOK_SETTING, url)
    return {"ok": True, "configured": True, "webhook_url": url}


@router.post("/settings/test")
async def n8n_test_saved_settings(_admin=Depends(require_admin), pool=Depends(get_pool)):
    cfg = await N8nConfig.resolve(pool)
    if not cfg.is_configured:
        raise HTTPException(400, "n8n webhook URL is not configured")
    service = N8nService(cfg, pool=pool)
    payload = build_connectivity_test_payload()
    result = await service.send_test_event(payload)
    now = datetime.now(timezone.utc).isoformat()
    status = "connected" if result.ok else "failed"
    await followups_repo.set_setting(pool, SETTING_LAST_TEST, now)
    await followups_repo.set_setting(pool, SETTING_LAST_STATUS, status)
    if not result.ok:
        raise HTTPException(502, result.error or "n8n connection test failed")
    return {
        "ok": True,
        "status": status,
        "status_code": result.status_code,
        "last_tested_at": now,
        "response_preview": result.response_preview,
        "message": "Connected to n8n",
    }


@router.post("/test")
async def n8n_test(body: N8nTestBody, _admin=Depends(require_admin), pool=Depends(get_pool)):
    """Send a synthetic test event to the configured n8n webhook."""
    cfg = await N8nConfig.resolve(pool, client_id=body.client_id)
    service = N8nService(cfg, pool=pool)
    if not service.is_configured() and not body.dry_run:
        raise HTTPException(
            400,
            "N8N_LEAD_WEBHOOK_URL is not configured. Set it in Admin → Webhooks → N8N Follow-up Workflow.",
        )

    payload = build_test_payload(client_id=body.client_id) if body.dry_run else build_connectivity_test_payload()
    if body.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "payload": payload,
            "field_sources": PAYLOAD_FIELD_SOURCES,
        }

    result = await service.send_test_event(payload)
    if result.skipped:
        raise HTTPException(400, result.error or "n8n not configured")
    if not result.ok:
        raise HTTPException(502, result.error or "n8n request failed")

    return {
        "ok": True,
        "status_code": result.status_code,
        "response_preview": result.response_preview,
    }
