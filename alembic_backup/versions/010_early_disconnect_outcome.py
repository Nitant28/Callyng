"""Add Early_Disconnect to outcome_callback for pyramid script configs."""

import json
from alembic import op
import sqlalchemy as sa

revision = "010_early_disconnect_outcome"
down_revision = "009_calllog_indexes"
branch_labels = None
depends_on = None

_SCRIPT_IDS = ("pyramid_bilingual", "pyramid_hi", "pyramid_mr", "prowave")
_OUTCOME = "Early_Disconnect"


def upgrade() -> None:
    bind = op.get_bind()
    for script_id in _SCRIPT_IDS:
        row = bind.execute(
            sa.text(
                """
                SELECT outcome_callback FROM script_configs
                WHERE script_id = :script_id
                LIMIT 1
                """
            ),
            {"script_id": script_id},
        ).fetchone()
        if not row:
            continue
        current = row[0] or []
        if isinstance(current, str):
            current = json.loads(current)
        values = list(current) if isinstance(current, list) else []
        if _OUTCOME not in values:
            values.append(_OUTCOME)
        updated = json.dumps(values)
        bind.execute(
            sa.text(
                """
                UPDATE script_configs
                SET outcome_callback = CAST(:outcome_callback AS jsonb)
                WHERE script_id = :script_id
                """
            ),
            {"script_id": script_id, "outcome_callback": updated},
        )
    print("010_early_disconnect_outcome: Updated pyramid script_configs outcome_callback.")


def downgrade() -> None:
    pass
