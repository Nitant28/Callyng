"""Migrate legacy cascade model IDs to 2026 catalog refresh."""

from pathlib import Path
import re

from alembic import op

revision = "013_catalog_2026_refresh"
down_revision = "012_cascade_provider_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path("db/schema/013_catalog_2026_refresh.sql").read_text(encoding="utf-8")
    statements = re.split(r';\s*$', sql, flags=re.MULTILINE)
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            op.get_bind().exec_driver_sql(stmt)


def downgrade() -> None:
    pass
