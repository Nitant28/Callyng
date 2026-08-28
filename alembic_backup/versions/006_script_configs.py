"""Add script_configs and script_config_revisions tables."""

from pathlib import Path
import re
from alembic import op

revision = "006_script_configs"
down_revision = "005_credit_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/006_script_configs.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
