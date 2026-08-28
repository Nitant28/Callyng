"""merge main and event migration branches

Revision ID: eebc32fa0aae
Revises: 011_bot_fixed_start_credits, 0b21f2c548c1
Create Date: 2026-08-17 05:05:08.656577

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'eebc32fa0aae'
down_revision: Union[str, Sequence[str], None] = ('011_bot_fixed_start_credits', '0b21f2c548c1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
