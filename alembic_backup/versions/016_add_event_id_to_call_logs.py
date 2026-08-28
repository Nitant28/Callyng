"""Add event_id to call_logs."""

from alembic import op


revision = "016_add_event_id_to_call_logs"
down_revision = "9b991e80fda4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE call_logs
        ADD COLUMN event_id UUID
        """
    )

    op.execute(
        """
        ALTER TABLE call_logs
        ADD CONSTRAINT fk_call_logs_event_id_events
        FOREIGN KEY (event_id)
        REFERENCES events(id)
        """
    )

    op.execute(
        """
        CREATE INDEX idx_call_logs_event
        ON call_logs (event_id)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_call_logs_event"
    )

    op.execute(
        """
        ALTER TABLE call_logs
        DROP CONSTRAINT IF EXISTS fk_call_logs_event_id_events
        """
    )

    op.execute(
        """
        ALTER TABLE call_logs
        DROP COLUMN IF EXISTS event_id
        """
    )
