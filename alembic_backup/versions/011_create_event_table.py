"""add events table

Revision ID: 5ef6991f5b34
Revises: 010_early_disconnect_outcome
Create Date: 2026-08-14 07:41:59.956857

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "5ef6991f5b34"
down_revision: Union[str, Sequence[str], None] = "010_early_disconnect_outcome"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
            "source_type",
            sa.String(50),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="draft",
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
            "retry_delay_minutes",
            sa.Integer(),
            nullable=True,
            server_default="120",
        ),
        sa.Column(
            "scheduled_start_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
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


def downgrade() -> None:
    op.drop_index(
        "idx_events_client_id",
        table_name="events",
    )

    op.drop_table("events")