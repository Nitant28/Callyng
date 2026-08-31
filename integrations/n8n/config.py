"""n8n remote webhook configuration (env-only — no secrets in source)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class N8nConfig:
    base_url: str
    lead_webhook_url: str
    webhook_secret: str | None
    timeout_seconds: int

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
        # Prefer explicit lead URL; accept follow-up alias used in ops docs.
        lead_url = (
            (os.getenv("N8N_LEAD_WEBHOOK_URL") or "").strip()
            or (os.getenv("N8N_FOLLOWUP_WEBHOOK_URL") or "").strip()
        )
        return cls(
            base_url=(os.getenv("N8N_BASE_URL") or "").strip().rstrip("/"),
            lead_webhook_url=lead_url,
            webhook_secret=secret,
            timeout_seconds=timeout,
        )

    @classmethod
    async def resolve(cls, pool=None) -> "N8nConfig":
        """Env config with optional DB override (integration_settings.n8n_lead_webhook_url)."""
        cfg = cls.from_env()
        if pool is None:
            return cfg
        try:
            from followups import repository as followups_repo

            db_url = await followups_repo.get_setting(pool, "n8n_lead_webhook_url")
            if db_url and str(db_url).strip():
                return cls(
                    base_url=cfg.base_url,
                    lead_webhook_url=str(db_url).strip(),
                    webhook_secret=cfg.webhook_secret,
                    timeout_seconds=cfg.timeout_seconds,
                )
        except Exception:
            pass
        return cfg
