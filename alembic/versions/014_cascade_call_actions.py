"""Add cascade transfer and live-tools toggles on script_configs."""

from pathlib import Path
import re

from alembic import op

revision = "014_cascade_call_actions"
down_revision = "013_catalog_2026_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/014_cascade_call_actions.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
