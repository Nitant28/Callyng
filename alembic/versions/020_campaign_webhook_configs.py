"""Scope webhook_configs to campaign_id + event (no client-global routing).

Pre-campaign rows are QUARANTINED into webhook_configs_legacy_backup
(never mapped with guessed campaign IDs). Live webhook_configs is then
cleared so campaign_id can be NOT NULL.

HMAC ``secret`` is retained — used for ``X-Aakashvani-Signature``.
"""

from alembic import op

revision = "020_campaign_webhook_configs"
down_revision = "019_campaign_follow_up_target"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve any pre-campaign (client_id, event) rows for manual recovery.
    # Do NOT invent campaign_id mappings.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_configs_legacy_backup (
            LIKE webhook_configs INCLUDING DEFAULTS
        )
        """
    )
    # Ensure quarantine metadata columns exist even if table was created earlier.
    op.execute(
        """
        ALTER TABLE webhook_configs_legacy_backup
            ADD COLUMN IF NOT EXISTS quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ADD COLUMN IF NOT EXISTS quarantine_reason TEXT NOT NULL DEFAULT 'pre_campaign_webhook_unmapped'
        """
    )
    op.execute(
        """
        INSERT INTO webhook_configs_legacy_backup (
            id, client_id, event, url, secret, active, created_at,
            quarantined_at, quarantine_reason
        )
        SELECT
            id, client_id, event, url, secret, active, created_at,
            NOW(), 'pre_campaign_webhook_unmapped'
        FROM webhook_configs w
        WHERE NOT EXISTS (
            SELECT 1 FROM webhook_configs_legacy_backup b WHERE b.id = w.id
        )
        """
    )

    # Live table must be empty before adding NOT NULL campaign_id.
    op.execute("DELETE FROM webhook_configs")

    op.execute(
        "ALTER TABLE webhook_configs DROP CONSTRAINT IF EXISTS webhook_configs_client_id_event_key"
    )
    op.execute(
        """
        ALTER TABLE webhook_configs
          ADD COLUMN IF NOT EXISTS campaign_id UUID
        """
    )
    # Enforce NOT NULL after column exists (safe on empty table).
    op.execute(
        """
        ALTER TABLE webhook_configs
          ALTER COLUMN campaign_id SET NOT NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_webhook_configs_campaign'
          ) THEN
            ALTER TABLE webhook_configs
              ADD CONSTRAINT fk_webhook_configs_campaign
              FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_webhook_configs_campaign_event'
          ) THEN
            ALTER TABLE webhook_configs
              ADD CONSTRAINT uq_webhook_configs_campaign_event UNIQUE (campaign_id, event);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhook_configs_client_campaign
          ON webhook_configs (client_id, campaign_id)
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_configs
          ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          ADD COLUMN IF NOT EXISTS last_tested_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS last_test_status VARCHAR(32)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE webhook_configs DROP COLUMN IF EXISTS last_test_status")
    op.execute("ALTER TABLE webhook_configs DROP COLUMN IF EXISTS last_tested_at")
    op.execute("ALTER TABLE webhook_configs DROP COLUMN IF EXISTS updated_at")
    op.execute("DROP INDEX IF EXISTS idx_webhook_configs_client_campaign")
    op.execute(
        "ALTER TABLE webhook_configs DROP CONSTRAINT IF EXISTS uq_webhook_configs_campaign_event"
    )
    op.execute(
        "ALTER TABLE webhook_configs DROP CONSTRAINT IF EXISTS fk_webhook_configs_campaign"
    )
    op.execute("ALTER TABLE webhook_configs DROP COLUMN IF EXISTS campaign_id")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'webhook_configs_client_id_event_key'
          ) THEN
            ALTER TABLE webhook_configs
              ADD CONSTRAINT webhook_configs_client_id_event_key UNIQUE (client_id, event);
          END IF;
        END $$;
        """
    )
    # Intentionally keep webhook_configs_legacy_backup for operator review.
