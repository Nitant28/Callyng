"""Add bot_configs and legacy schema compat from db/schema/002_compat.sql."""

from pathlib import Path
import re
from alembic import op
from sqlalchemy import text

revision = "002_compat"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/002_compat.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
