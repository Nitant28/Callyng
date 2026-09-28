"""Follow-up event retry / failure observability columns."""

from alembic import op

revision = "023_follow_up_event_retries"
down_revision = "022_campaign_lead_field_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE follow_up_events
          ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS error_category VARCHAR(40),
          ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_follow_up_events_retry
          ON follow_up_events (client_id, status, next_retry_at)
          WHERE status IN ('failed', 'retrying')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_follow_up_events_retry")
    op.execute("ALTER TABLE follow_up_events DROP COLUMN IF EXISTS next_retry_at")
    op.execute("ALTER TABLE follow_up_events DROP COLUMN IF EXISTS last_attempted_at")
    op.execute("ALTER TABLE follow_up_events DROP COLUMN IF EXISTS error_category")
    op.execute("ALTER TABLE follow_up_events DROP COLUMN IF EXISTS attempt_count")
