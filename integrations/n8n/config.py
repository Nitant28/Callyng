"""n8n remote webhook configuration (env + DB overrides)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

GLOBAL_WEBHOOK_SETTING = "n8n_lead_webhook_url"


def client_webhook_setting_key(client_id: UUID) -> str:
    return f"n8n_lead_webhook_url:{client_id}"


@dataclass(frozen=True)
class N8nConfig:
    base_url: str
    lead_webhook_url: str
    webhook_secret: str | None
    timeout_seconds: int
    url_source: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.lead_webhook_url)

    @classmethod
    def from_env(cls) -> "N8nConfig":
        timeout = 15
        try:
            timeout = max(5, int(os.getenv("N8N_TIMEOUT_SECONDS", "15")))
        except ValueError:
            pass
        secret = (os.getenv("N8N_WEBHOOK_SECRET") or "").strip() or None
        lead_url = (
            (os.getenv("N8N_LEAD_WEBHOOK_URL") or "").strip()
            or (os.getenv("N8N_FOLLOWUP_WEBHOOK_URL") or "").strip()
        )
        return cls(
            base_url=(os.getenv("N8N_BASE_URL") or "").strip().rstrip("/"),
            lead_webhook_url=lead_url,
            webhook_secret=secret,
            timeout_seconds=timeout,
            url_source="env" if lead_url else None,
        )

    @classmethod
    async def resolve(cls, pool=None, *, client_id: UUID | None = None) -> "N8nConfig":
        """Resolve webhook URL with precedence:

        1. Client-specific DB setting ``n8n_lead_webhook_url:{client_id}``
        2. Global DB setting ``n8n_lead_webhook_url``
        3. ``N8N_LEAD_WEBHOOK_URL`` / ``N8N_FOLLOWUP_WEBHOOK_URL`` env fallback
        """
        cfg = cls.from_env()
        if pool is None:
            return cfg
        try:
            from followups import repository as followups_repo

            if client_id is not None:
                client_url = await followups_repo.get_setting(pool, client_webhook_setting_key(client_id))
                if client_url and str(client_url).strip():
                    return cls(
                        base_url=cfg.base_url,
                        lead_webhook_url=str(client_url).strip(),
                        webhook_secret=cfg.webhook_secret,
                        timeout_seconds=cfg.timeout_seconds,
                        url_source="database_client",
                    )

            db_url = await followups_repo.get_setting(pool, GLOBAL_WEBHOOK_SETTING)
            if db_url and str(db_url).strip():
                return cls(
                    base_url=cfg.base_url,
                    lead_webhook_url=str(db_url).strip(),
                    webhook_secret=cfg.webhook_secret,
                    timeout_seconds=cfg.timeout_seconds,
                    url_source="database_global",
                )
        except Exception:
            pass
        return cfg
