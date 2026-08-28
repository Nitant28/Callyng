"""make events always active

Revision ID: 9b991e80fda4
Revises: eebc32fa0aae
Create Date: 2026-08-17 09:42:02.490105
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b991e80fda4"
down_revision: Union[str, Sequence[str], None] = "eebc32fa0aae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Events are always active.
    op.execute(
        """
        UPDATE events
        SET status = 'active'
        """
    )

    op.alter_column(
        "events",
        "status",
        server_default=sa.text("'active'"),
    )

    # Events do not have a completion lifecycle.
    op.drop_column("events", "completed_at")


def downgrade() -> None:
    # Restore the completion field.
    op.add_column(
        "events",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Restore the previous default.
    op.alter_column(
        "events",
        "status",
        server_default=sa.text("'draft'"),
    )