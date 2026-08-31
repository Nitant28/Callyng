"""Add campaigns.budget_returned_at for idempotent credit return."""

from pathlib import Path
import re
from alembic import op

revision = "003_campaign_settlement"
down_revision = "002_compat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/003_campaign_settlement.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
