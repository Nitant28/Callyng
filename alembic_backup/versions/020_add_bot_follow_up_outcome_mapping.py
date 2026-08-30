"""add bot follow up outcome mapping

Revision ID: cb22f0e412ab
Revises: ffdf98a99d6b
Create Date: 2026-08-24 13:08:48.960735
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "cb22f0e412ab"
down_revision: Union[str, Sequence[str], None] = "ffdf98a99d6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "script_configs",
        sa.Column(
            "outcome_bot_follow_up",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_configs", "outcome_bot_follow_up")