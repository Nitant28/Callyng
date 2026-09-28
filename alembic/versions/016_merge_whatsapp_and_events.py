"""Merge WhatsApp follow-up and events/cascade migration branches."""

from typing import Sequence, Union

from alembic import op

revision: str = "016_merge_whatsapp_and_events"
down_revision: Union[str, Sequence[str], None] = (
    "013_follow_up_events",
    "015_clean_event_schema",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
