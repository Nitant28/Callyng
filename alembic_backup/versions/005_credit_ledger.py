"""Add credit_transactions ledger."""

from pathlib import Path
import re
from alembic import op

revision = "005_credit_ledger"
down_revision = "004_campaign_max_call_minutes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    sql = Path("db/schema/005_credit_ledger.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)

def downgrade() -> None:
    pass
