"""Campaign follow-up target + unique WhatsApp phone_number_id (non-null)."""

from alembic import op

revision = "019_campaign_follow_up_target"
down_revision = "018_campaign_n8n_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE campaigns
          ADD COLUMN IF NOT EXISTS follow_up_target VARCHAR(40)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_integrations_phone_number_id
          ON whatsapp_integrations (phone_number_id)
          WHERE phone_number_id IS NOT NULL AND btrim(phone_number_id) <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_whatsapp_integrations_phone_number_id")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS follow_up_target")
