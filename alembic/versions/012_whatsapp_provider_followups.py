"""Extend WhatsApp integrations for multi-provider + follow-ups.

Does not drop existing Messages tables. Adds provider history on messages
and follow-up job cancellation support.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "012_whatsapp_provider_followups"
down_revision = "011_whatsapp_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("whatsapp_integrations_provider_check", "whatsapp_integrations", type_="check")
    op.create_check_constraint(
        "whatsapp_integrations_provider_check",
        "whatsapp_integrations",
        "provider IN ('stub', 'meta_cloud', 'finbite', 'wapi', 'aakashvani_managed', 'custom', 'other')",
    )

    op.add_column(
        "whatsapp_integrations",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "whatsapp_integrations",
        sa.Column("configuration", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "whatsapp_integrations",
        sa.Column("connection_status", sa.String(40), nullable=False, server_default="untested"),
    )
    op.add_column(
        "whatsapp_integrations",
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column("whatsapp_messages", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column(
        "whatsapp_messages",
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "whatsapp_messages",
        sa.Column("idempotency_key", sa.String(255), nullable=True),
    )
    op.create_index(
        "uq_whatsapp_messages_idempotency",
        "whatsapp_messages",
        ["client_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "whatsapp_followup_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_outcome", sa.String(80), nullable=False, server_default="Interested"),
        sa.Column("steps", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_whatsapp_followup_plans_client", "whatsapp_followup_plans", ["client_id"])

    op.create_table(
        "whatsapp_followup_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("whatsapp_followup_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("whatsapp_conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_phone", sa.String(30), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("cancel_reason", sa.String(80), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("whatsapp_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'cancelled', 'failed')",
            name="whatsapp_followup_jobs_status_check",
        ),
    )
    op.create_index(
        "idx_whatsapp_followup_jobs_due",
        "whatsapp_followup_jobs",
        ["client_id", "scheduled_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_followup_jobs")
    op.drop_table("whatsapp_followup_plans")
    op.drop_index("uq_whatsapp_messages_idempotency", table_name="whatsapp_messages")
    op.drop_column("whatsapp_messages", "idempotency_key")
    op.drop_column("whatsapp_messages", "lead_id")
    op.drop_column("whatsapp_messages", "provider")
    op.drop_column("whatsapp_integrations", "last_tested_at")
    op.drop_column("whatsapp_integrations", "connection_status")
    op.drop_column("whatsapp_integrations", "configuration")
    op.drop_column("whatsapp_integrations", "enabled")
    op.drop_constraint("whatsapp_integrations_provider_check", "whatsapp_integrations", type_="check")
    op.create_check_constraint(
        "whatsapp_integrations_provider_check",
        "whatsapp_integrations",
        "provider IN ('stub', 'meta_cloud', 'other')",
    )
