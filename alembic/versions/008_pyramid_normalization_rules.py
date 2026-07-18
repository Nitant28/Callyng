"""Backfill pyramid normalization rules."""

import json
from alembic import op
import sqlalchemy as sa

from sts_scripts.pyramid_extraction import PYRAMID_NORMALIZATION_RULES

revision = "008_pyramid_normalization_rules"
down_revision = "007_remove_dnc"
branch_labels = None
depends_on = None

def upgrade() -> None:
    rules_json = json.dumps(PYRAMID_NORMALIZATION_RULES)
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        UPDATE script_configs
        SET normalization_rules = CAST(:rules AS jsonb)
        WHERE script_id IN ('pyramid_bilingual', 'pyramid_hi', 'pyramid_mr', 'prowave')
          AND (normalization_rules IS NULL OR normalization_rules = '[]'::jsonb);
    """).bindparams(rules=rules_json))
    print(f"008_pyramid_normalization_rules: Migrated {result.rowcount} script_configs rows.")

def downgrade() -> None:
    # Intentionally do not downgrade to avoid breaking patched live configs
    pass
