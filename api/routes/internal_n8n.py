"""Admin endpoints for remote n8n connectivity tests."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from api.auth import get_pool, require_admin
from followups import repository as followups_repo
from followups.interested import DEFAULT_FOLLOW_UP_TARGET, FOLLOW_UP_TARGET_OPTIONS
from integrations.n8n.config import GLOBAL_WEBHOOK_SETTING, N8nConfig
from integrations.n8n.payload import PAYLOAD_FIELD_SOURCES, build_test_payload
from integrations.n8n import workflows as n8n_workflows

router = APIRouter(prefix="/internal/n8n", tags=["internal-n8n"])

SETTING_LAST_TEST = "n8n_webhook_last_tested_at"
SETTING_LAST_STATUS = "n8n_webhook_last_test_status"
SETTING_FOLLOW_UP_TARGET = "n8n_follow_up_target"


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


class N8nFollowUpTargetBody(BaseModel):
    follow_up_target: str = Field(
        ...,
        validation_alias=AliasChoices("follow_up_target", "followUpTarget"),
    )


_LEGACY_GLOBAL_GONE = (
    "Global N8N follow-up configuration is retired. "
    "Configure campaign-scoped webhooks at Admin → Webhooks "
    "(client → campaign → event → URL) and use "
    "POST /internal/webhook-configs/{id}/test for connectivity."
)


@router.get("/status")
async def n8n_status(_admin=Depends(require_admin), pool=Depends(get_pool)):
    """Deprecated read-only status. Does not participate in event dispatch."""
    cfg = await N8nConfig.resolve(pool)
    env_cfg = N8nConfig.from_env()
    db_url = await followups_repo.get_setting(pool, GLOBAL_WEBHOOK_SETTING)
    last_tested = await followups_repo.get_setting(pool, SETTING_LAST_TEST)
    last_status = await followups_repo.get_setting(pool, SETTING_LAST_STATUS)
    source = cfg.url_source or ("env" if env_cfg.lead_webhook_url else None)
    return {
        "configured": cfg.is_configured,
        "deprecated": True,
        "dispatch_note": "Event dispatch uses campaign webhook_configs only; this status is informational.",
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
    """Deprecated read-only view of legacy global settings. Not used for dispatch."""
    db_url = await followups_repo.get_setting(pool, GLOBAL_WEBHOOK_SETTING)
    env_cfg = N8nConfig.from_env()
    effective = await N8nConfig.resolve(pool)
    url = db_url or env_cfg.lead_webhook_url or ""
    return {
        "deprecated": True,
        "dispatch_note": "Legacy global URL is ignored by campaign event dispatch.",
        "webhook_url": url,
        "configured": effective.is_configured,
        "source": "database" if db_url else ("env" if env_cfg.lead_webhook_url else None),
        "follow_up_target": await followups_repo.get_setting(pool, SETTING_FOLLOW_UP_TARGET) or DEFAULT_FOLLOW_UP_TARGET,
        "follow_up_target_options": FOLLOW_UP_TARGET_OPTIONS,
        "precedence": [
            "RETIRED — campaign webhook_configs(campaign_id, event) only",
        ],
    }


@router.put("/settings/follow-up-target")
async def n8n_save_follow_up_target(
    body: N8nFollowUpTargetBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    raise HTTPException(410, _LEGACY_GLOBAL_GONE)


@router.put("/settings")
async def n8n_save_settings(body: N8nSettingsBody, _admin=Depends(require_admin), pool=Depends(get_pool)):
    raise HTTPException(410, _LEGACY_GLOBAL_GONE)


@router.post("/settings/test")
async def n8n_test_saved_settings(_admin=Depends(require_admin), pool=Depends(get_pool)):
    raise HTTPException(410, _LEGACY_GLOBAL_GONE)


@router.post("/test")
async def n8n_test(body: N8nTestBody, _admin=Depends(require_admin), pool=Depends(get_pool)):
    """Dry-run payload inspection only. Live global POSTs are disabled."""
    if not body.dry_run:
        raise HTTPException(410, _LEGACY_GLOBAL_GONE)

    payload = build_test_payload(client_id=body.client_id)
    return {
        "ok": True,
        "dry_run": True,
        "payload": payload,
        "field_sources": PAYLOAD_FIELD_SOURCES,
    }


# ── Workflow registry (inert: does not change runtime dispatch) ────────


class CreateN8nWorkflowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    webhook_url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        validation_alias=AliasChoices("webhook_url", "webhookUrl"),
    )
    description: str | None = None
    enabled: bool = True


class PatchN8nWorkflowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    webhook_url: str | None = Field(
        default=None,
        max_length=2048,
        validation_alias=AliasChoices("webhook_url", "webhookUrl"),
    )
    description: str | None = None
    enabled: bool | None = None


class N8nWorkflowTestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True


def _workflow_http_error(exc: n8n_workflows.WorkflowError) -> HTTPException:
    if exc.code == "not_found":
        return HTTPException(404, exc.message)
    return HTTPException(400, exc.message)


@router.get("/workflows")
async def list_n8n_workflows(_admin=Depends(require_admin), pool=Depends(get_pool)):
    rows = await n8n_workflows.list_workflows(pool)
    return {"workflows": rows}


@router.post("/workflows")
async def create_n8n_workflow(
    body: CreateN8nWorkflowBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    try:
        row = await n8n_workflows.create_workflow(
            pool,
            name=body.name,
            webhook_url=body.webhook_url,
            description=body.description,
            enabled=body.enabled,
        )
    except n8n_workflows.WorkflowError as exc:
        raise _workflow_http_error(exc) from exc
    return {"ok": True, "workflow": row}


@router.get("/workflows/{workflow_id}")
async def get_n8n_workflow(
    workflow_id: UUID,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    row = await n8n_workflows.get_workflow(pool, workflow_id)
    if not row:
        raise HTTPException(404, "Workflow not found")
    return {"workflow": row}


@router.patch("/workflows/{workflow_id}")
async def patch_n8n_workflow(
    workflow_id: UUID,
    body: PatchN8nWorkflowBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No workflow fields to update")
    try:
        row = await n8n_workflows.update_workflow(pool, workflow_id, fields=fields)
    except n8n_workflows.WorkflowError as exc:
        raise _workflow_http_error(exc) from exc
    if not row:
        raise HTTPException(404, "Workflow not found")
    return {"ok": True, "workflow": row}


@router.delete("/workflows/{workflow_id}")
async def delete_n8n_workflow(
    workflow_id: UUID,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    try:
        row = await n8n_workflows.delete_workflow(pool, workflow_id)
    except n8n_workflows.WorkflowError as exc:
        raise _workflow_http_error(exc) from exc
    if not row:
        raise HTTPException(404, "Workflow not found")
    return {"ok": True, "workflow": row}


@router.post("/workflows/{workflow_id}/test")
async def test_n8n_workflow(
    workflow_id: UUID,
    body: N8nWorkflowTestBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    """Record connectivity-test metadata. Live n8n POST is disabled in Release 2."""
    if not body.dry_run:
        raise HTTPException(
            400,
            "Live workflow tests are disabled until the resolver release. Use dry_run=true.",
        )
    try:
        result = await n8n_workflows.record_dry_test(pool, workflow_id)
    except n8n_workflows.WorkflowError as exc:
        raise _workflow_http_error(exc) from exc
    return {"ok": True, **result}


class PlatformDefaultWorkflowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("workflow_id", "workflowId"),
    )


@router.get("/settings/platform-default-workflow")
async def get_platform_default_workflow(_admin=Depends(require_admin), pool=Depends(get_pool)):
    from integrations.n8n.routing import PLATFORM_DEFAULT_WORKFLOW_SETTING, get_platform_default_workflow_id

    workflow_id = await get_platform_default_workflow_id(pool)
    workflow = None
    if workflow_id:
        workflow = await n8n_workflows.get_workflow(pool, workflow_id)
    return {
        "setting": PLATFORM_DEFAULT_WORKFLOW_SETTING,
        "workflow_id": str(workflow_id) if workflow_id else None,
        "workflow": workflow,
    }


@router.put("/settings/platform-default-workflow")
async def put_platform_default_workflow(
    body: PlatformDefaultWorkflowBody,
    _admin=Depends(require_admin),
    pool=Depends(get_pool),
):
    raise HTTPException(410, _LEGACY_GLOBAL_GONE)
