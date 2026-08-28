"""add event support to leads

Revision ID: 620ac34a3fb8
Revises: 012_event_outcome_bot_mappings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "620ac34a3fb8"
down_revision: Union[str, Sequence[str], None] = "012_event_outcome_bot_mappings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow leads to exist without a campaign.
    op.alter_column(
        "leads",
        "campaign_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Add event membership.
    op.add_column(
        "leads",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_leads_event_id_events",
        "leads",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Prevent the same phone from being added twice to the same event.
    op.create_unique_constraint(
        "uq_leads_event_id_phone",
        "leads",
        ["event_id", "phone"],
    )

    op.create_index(
        "idx_leads_event_id",
        "leads",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_leads_event_id",
        table_name="leads",
    )

    op.drop_constraint(
        "uq_leads_event_id_phone",
        "leads",
        type_="unique",
    )

    op.drop_constraint(
        "fk_leads_event_id_events",
        "leads",
        type_="foreignkey",
    )

    op.drop_column(
        "leads",
        "event_id",
    )

    op.alter_column(
        "leads",
        "campaign_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )