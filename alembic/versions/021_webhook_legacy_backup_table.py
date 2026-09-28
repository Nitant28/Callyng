"""Ensure webhook_configs_legacy_backup exists for environments that already
ran the earlier destructive 020 (DELETE without quarantine).

Does not invent campaign mappings. Does not restore deleted rows
(those were not recoverable once deleted without a prior dump).
"""

from alembic import op

revision = "021_webhook_legacy_backup_table"
down_revision = "020_campaign_webhook_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent safety net: 020 already creates + populates this table on
    # fresh upgrades. This revision covers DBs that applied a prior empty/broken
    # 020 that deleted live rows without quarantine.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_configs_legacy_backup (
            id UUID PRIMARY KEY,
            client_id UUID,
            event VARCHAR(50),
            url TEXT,
            secret VARCHAR(255),
            active BOOLEAN,
            created_at TIMESTAMPTZ,
            quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            quarantine_reason TEXT NOT NULL DEFAULT 'pre_campaign_webhook_unmapped'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_configs_legacy_backup
          ADD COLUMN IF NOT EXISTS quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          ADD COLUMN IF NOT EXISTS quarantine_reason TEXT NOT NULL DEFAULT 'pre_campaign_webhook_unmapped'
        """
    )


def downgrade() -> None:
    # Keep backup table; dropping would destroy quarantine evidence.
    pass
