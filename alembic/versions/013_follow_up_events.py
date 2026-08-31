"""Follow-up event log + integration settings (n8n webhook override)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "013_follow_up_events"
down_revision = "012_whatsapp_provider_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follow_up_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(30), nullable=False, server_default="n8n"),
        sa.Column("direction", sa.String(20), nullable=False, server_default="outgoing"),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("source", sa.String(30), nullable=False, server_default="auto"),
        sa.Column("message_preview", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("session_call_id", sa.String(120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_follow_up_events_lead", "follow_up_events", ["client_id", "lead_id", "created_at"])
    op.create_index(
        "uq_follow_up_events_idempotency",
        "follow_up_events",
        ["client_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "integration_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("integration_settings")
    op.drop_index("uq_follow_up_events_idempotency", table_name="follow_up_events")
    op.drop_index("idx_follow_up_events_lead", table_name="follow_up_events")
    op.drop_table("follow_up_events")
