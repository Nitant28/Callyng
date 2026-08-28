"""Add cascade_tts_model and per-role settings JSONB columns."""

from pathlib import Path
import re

from alembic import op

revision = "012_cascade_provider_settings"
down_revision = "011_bot_fixed_start_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/012_cascade_provider_settings.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
