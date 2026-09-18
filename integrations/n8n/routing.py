"""Resolve campaign-scoped n8n webhook destinations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from integrations.n8n.config import N8nConfig

SOURCE_CAMPAIGN_WEBHOOK = "campaign_webhook"
SOURCE_NONE = "none"
PLATFORM_DEFAULT_WORKFLOW_SETTING = "n8n_platform_default_workflow_id"


@dataclass
class ResolvedWorkflow:
    ok: bool
    webhook_url: str | None = None
    source: str = SOURCE_NONE
    webhook_secret: str | None = None
    event: str | None = None
    error: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "webhook_url": self.webhook_url,
            "source": self.source,
            "event": self.event,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "error": self.error,
        }


def n8n_config_for(dest: ResolvedWorkflow) -> N8nConfig:
    env = N8nConfig.from_env()
    return N8nConfig(
        base_url=env.base_url,
        lead_webhook_url=dest.webhook_url or "",
        webhook_secret=dest.webhook_secret or env.webhook_secret,
        timeout_seconds=env.timeout_seconds,
        url_source=dest.source,
    )


async def get_platform_default_workflow_id(pool) -> UUID | None:
    if pool is None:
        return None
    try:
        from followups import repository as followups_repo

        raw = await followups_repo.get_setting(pool, PLATFORM_DEFAULT_WORKFLOW_SETTING)
        if not raw:
            return None
        return UUID(str(raw))
    except Exception:
        return None


async def resolve_campaign_webhook(
    pool,
    *,
    client_id: UUID,
    campaign_id: UUID,
    event: str,
    campaign: dict[str, Any] | None = None,
) -> ResolvedWorkflow:
    """Resolve the single campaign+event webhook. Fail closed if missing."""
    _ = campaign
    if pool is None:
        return ResolvedWorkflow(
            ok=False,
            source=SOURCE_NONE,
            event=event,
            error="pool_unavailable",
        )
    try:
        # Physical columns are url/secret (see db.postgres.upsert_webhook_config).
        row = await pool.fetchrow(
            """
            SELECT id, url, secret, active, event
            FROM webhook_configs
            WHERE client_id = $1
              AND campaign_id = $2
              AND event = $3
              AND active = TRUE
            ORDER BY updated_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            client_id,
            campaign_id,
            event,
        )
    except Exception as exc:
        return ResolvedWorkflow(
            ok=False,
            source=SOURCE_NONE,
            event=event,
            error=f"webhook_lookup_failed:{type(exc).__name__}",
        )

    if not row or not str(row.get("url") or "").strip():
        return ResolvedWorkflow(
            ok=False,
            source=SOURCE_NONE,
            event=event,
            error="no_webhook_configured_for_campaign_event",
        )

    secret = row.get("secret")
    return ResolvedWorkflow(
        ok=True,
        webhook_url=str(row["url"]).strip(),
        source=SOURCE_CAMPAIGN_WEBHOOK,
        webhook_secret=(str(secret).strip() if secret else None),
        event=event,
        workflow_id=str(row["id"]) if row.get("id") else None,
        workflow_name=None,
    )
