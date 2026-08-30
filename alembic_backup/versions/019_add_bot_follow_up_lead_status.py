"""add bot follow up lead status

Revision ID: ffdf98a99d6b
Revises: ed200db85367
Create Date: 2026-08-24 10:26:39.796787

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'ffdf98a99d6b'
down_revision: Union[str, Sequence[str], None] = 'ed200db85367'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("leads_status_check", "leads", type_="check")

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
    op.drop_constraint("leads_status_check", "leads", type_="check")

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
