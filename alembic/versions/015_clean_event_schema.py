"""create final Event schema without WhatsApp changes"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "015_clean_event_schema"
down_revision: Union[str, Sequence[str], None] = "014_cascade_call_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # EVENTS
    # Events are always active.
    # No completed_at / completion lifecycle.
    # ============================================================
    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "primary_bot_config_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "max_concurrent_calls",
            sa.Integer(),
            nullable=True,
            server_default="5",
        ),
        sa.Column(
            "calls_per_minute",
            sa.Integer(),
            nullable=True,
            server_default="10",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=True,
            server_default="3",
        ),
        sa.Column(
            "total_leads",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "pending_leads",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "calling_leads",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "callback_leads",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "completed_leads",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "failed_leads",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "attempt_0_schedule_minutes",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "attempt_1_schedule_minutes",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "attempt_2_schedule_minutes",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "source_types",
            sa.ARRAY(sa.String(50)),
            nullable=True,
        ),
        sa.Column(
            "lead_handling",
            sa.String(50),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["primary_bot_config_id"],
            ["bot_configs.id"],
        ),
    )

    op.create_index(
        "idx_events_client_id",
        "events",
        ["client_id"],
    )

    # ============================================================
    # EVENT OUTCOME -> BOT MAPPINGS
    # ============================================================
    op.create_table(
        "event_outcome_bot_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.String(50),
            nullable=False,
        ),
        sa.Column(
            "bot_config_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bot_config_id"],
            ["bot_configs.id"],
        ),
        sa.UniqueConstraint(
            "event_id",
            "outcome",
            name="uq_event_outcome_bot_mappings_event_outcome",
        ),
    )

    op.create_index(
        "idx_event_outcome_bot_mappings_event",
        "event_outcome_bot_mappings",
        ["event_id"],
    )

    # ============================================================
    # LEADS
    # Campaign leads keep working as before.
    # Event leads use event_id instead of campaign_id.
    # ============================================================
    op.alter_column(
        "leads",
        "campaign_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.add_column(
        "leads",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_leads_event_id_events",
        "leads",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_unique_constraint(
        "uq_leads_event_id_phone",
        "leads",
        ["event_id", "phone"],
    )

    op.create_index(
        "idx_leads_event_id",
        "leads",
        ["event_id"],
    )

    # ============================================================
    # CALL LOGS
    # ============================================================
    op.add_column(
        "call_logs",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_call_logs_event_id_events",
        "call_logs",
        "events",
        ["event_id"],
        ["id"],
    )

    op.create_index(
        "idx_call_logs_event",
        "call_logs",
        ["event_id"],
    )

    # ============================================================
    # SCRIPT CONFIGS
    # Bot follow-up outcomes.
    # ============================================================
    op.add_column(
        "script_configs",
        sa.Column(
            "outcome_bot_follow_up",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # ============================================================
    # LEAD STATUS
    # Add bot_follow_up status.
    # ============================================================
    op.drop_constraint(
        "leads_status_check",
        "leads",
        type_="check",
    )

    op.create_check_constraint(
        "leads_status_check",
        "leads",
        """
        status IN (
            'pending',
            'calling',
            'bot_follow_up',
            'completed',
            'failed',
            'callback_scheduled'
        )
        """,
    )


def downgrade() -> None:
    # ============================================================
    # LEAD STATUS
    # Restore the original status constraint.
    # ============================================================
    op.drop_constraint(
        "leads_status_check",
        "leads",
        type_="check",
    )

    op.create_check_constraint(
        "leads_status_check",
        "leads",
        """
        status IN (
            'pending',
            'calling',
            'completed',
            'failed',
            'callback_scheduled'
        )
        """,
    )

    # ============================================================
    # SCRIPT CONFIGS
    # Remove bot follow-up outcomes.
    # ============================================================
    op.drop_column(
        "script_configs",
        "outcome_bot_follow_up",
    )

    # ============================================================
    # CALL LOGS
    # Remove Event support.
    # ============================================================
    op.drop_index(
        "idx_call_logs_event",
        table_name="call_logs",
    )

    op.drop_constraint(
        "fk_call_logs_event_id_events",
        "call_logs",
        type_="foreignkey",
    )

    op.drop_column(
        "call_logs",
        "event_id",
    )

    # ============================================================
    # LEADS
    # Remove Event support and restore campaign_id NOT NULL.
    # ============================================================
    op.drop_index(
        "idx_leads_event_id",
        table_name="leads",
    )

    op.drop_constraint(
        "uq_leads_event_id_phone",
        "leads",
        type_="unique",
    )

    op.drop_constraint(
        "fk_leads_event_id_events",
        "leads",
        type_="foreignkey",
    )

    op.drop_column(
        "leads",
        "event_id",
    )

    op.alter_column(
        "leads",
        "campaign_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # ============================================================
    # EVENT OUTCOME -> BOT MAPPINGS
    # ============================================================
    op.drop_index(
        "idx_event_outcome_bot_mappings_event",
        table_name="event_outcome_bot_mappings",
    )

    op.drop_table(
        "event_outcome_bot_mappings",
    )

    # ============================================================
    # EVENTS
    # ============================================================
    op.drop_index(
        "idx_events_client_id",
        table_name="events",
    )

    op.drop_table(
        "events",
    )
