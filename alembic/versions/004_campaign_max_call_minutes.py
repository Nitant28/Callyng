"""Add max_call_minutes to campaigns."""

from pathlib import Path
import re
from alembic import op
from sqlalchemy import text

revision = "004_campaign_max_call_minutes"
down_revision = "003_campaign_settlement"
branch_labels = None
depends_on = None

def upgrade() -> None:
    sql = Path("db/schema/004_campaign_max_call_minutes.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)

def downgrade() -> None:
    pass
