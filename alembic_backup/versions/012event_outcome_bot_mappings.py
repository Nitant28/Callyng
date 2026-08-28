"""add event outcome bot mappings

Revision ID: 012_event_outcome_bot_mappings
Revises: 5ef6991f5b34
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012_event_outcome_bot_mappings"
down_revision: Union[str, Sequence[str], None] = "5ef6991f5b34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index(
        "idx_event_outcome_bot_mappings_event",
        table_name="event_outcome_bot_mappings",
    )

    op.drop_table("event_outcome_bot_mappings")