"""Add bot_configs.fixed_start_credits and widen call_logs.billed_minutes."""

from pathlib import Path
import re
from alembic import op

revision = "011_bot_fixed_start_credits"
down_revision = "010_early_disconnect_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/011_bot_fixed_start_credits.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
