"""Add per-campaign lead_field_config JSONB for enabled/required lead fields."""

from alembic import op

revision = "022_campaign_lead_field_config"
down_revision = "021_webhook_legacy_backup_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE campaigns
        ADD COLUMN IF NOT EXISTS lead_field_config JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS lead_field_config")
