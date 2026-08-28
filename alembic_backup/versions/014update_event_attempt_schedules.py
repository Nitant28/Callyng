"""update event attempt schedules

Revision ID: 0b21f2c548c1
Revises: 620ac34a3fb8
Create Date: 2026-08-14 11:05:50.482512
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0b21f2c548c1"
down_revision: Union[str, Sequence[str], None] = "620ac34a3fb8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove old scheduling fields
    op.drop_column("events", "scheduled_start_at")
    op.drop_column("events", "retry_delay_minutes")

    # Schedule before the first call
    op.add_column(
        "events",
        sa.Column(
            "attempt_0_schedule_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Schedule before the second call
    op.add_column(
        "events",
        sa.Column(
            "attempt_1_schedule_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Schedule before the third call
    op.add_column(
        "events",
        sa.Column(
            "attempt_2_schedule_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Remove attempt schedules
    op.drop_column("events", "attempt_2_schedule_minutes")
    op.drop_column("events", "attempt_1_schedule_minutes")
    op.drop_column("events", "attempt_0_schedule_minutes")

    # Restore old fields
    op.add_column(
        "events",
        sa.Column(
            "retry_delay_minutes",
            sa.Integer(),
            nullable=True,
            server_default="120",
        ),
    )

    op.add_column(
        "events",
        sa.Column(
            "scheduled_start_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )