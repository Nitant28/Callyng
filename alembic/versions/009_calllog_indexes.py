"""Add partial indexes for dialer call_logs hot-path."""

from alembic import op
import sqlalchemy as sa


revision = "009_calllog_indexes"
down_revision = "008_pyramid_normalization_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Serves the "is there a live call for this lead?" NOT EXISTS
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_logs_lead_live
            ON call_logs (lead_id)
            WHERE in_progress = TRUE;
        """
    )
    
    # Serves the "did a call for this lead end recently?" NOT EXISTS (wrap-up grace)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_logs_lead_ended
            ON call_logs (lead_id, ended_at DESC)
            WHERE ended_at IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_call_logs_lead_ended;")
    op.execute("DROP INDEX IF EXISTS idx_call_logs_lead_live;")
