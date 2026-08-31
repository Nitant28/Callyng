"""WhatsApp / Messages tables (scaffold — no live provider payloads).

Provider-specific auth/send/webhook fields must follow client API documentation
before production use. Credentials are server-side only and never returned raw.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "011_whatsapp_messages"
down_revision = "010_early_disconnect_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="stub"),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("phone_number_id", sa.String(255), nullable=True),
        sa.Column("business_account_id", sa.String(255), nullable=True),
        sa.Column("webhook_verify_token", sa.String(255), nullable=True),
        # Opaque credential blob — never select into client/admin list APIs as plaintext.
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="inactive"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "provider IN ('stub', 'meta_cloud', 'other')",
            name="whatsapp_integrations_provider_check",
        ),
        sa.CheckConstraint(
            "status IN ('inactive', 'pending', 'active', 'error')",
            name="whatsapp_integrations_status_check",
        ),
    )
    op.create_index(
        "idx_whatsapp_integrations_client",
        "whatsapp_integrations",
        ["client_id"],
    )

    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "integration_id",
            UUID(as_uuid=True),
            sa.ForeignKey("whatsapp_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_phone", sa.String(30), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "integration_id",
            "customer_phone",
            name="uq_whatsapp_conversation_phone",
        ),
    )
    op.create_index(
        "idx_whatsapp_conversations_client_last",
        "whatsapp_conversations",
        ["client_id", "last_message_at"],
    )

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("message_type", sa.String(40), nullable=False, server_default="text"),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("template_name", sa.String(255), nullable=True),
        sa.Column("template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "direction IN ('incoming', 'outgoing')",
            name="whatsapp_messages_direction_check",
        ),
        sa.UniqueConstraint(
            "client_id",
            "provider_message_id",
            name="uq_whatsapp_provider_message",
        ),
    )
    op.create_index(
        "idx_whatsapp_messages_conversation_created",
        "whatsapp_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "whatsapp_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "integration_id",
            UUID(as_uuid=True),
            sa.ForeignKey("whatsapp_integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_template_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("language", sa.String(20), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("components", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_whatsapp_templates_client",
        "whatsapp_templates",
        ["client_id", "integration_id"],
    )


def downgrade() -> None:
    op.drop_table("whatsapp_templates")
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_conversations")
    op.drop_table("whatsapp_integrations")
