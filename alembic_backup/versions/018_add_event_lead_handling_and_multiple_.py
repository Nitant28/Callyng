"""add event lead handling and multiple sources

Revision ID: ed200db85367
Revises: 4f0cb771a4ab
Create Date: 2026-08-20 06:36:12.629515
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ed200db85367"

down_revision: Union[str, Sequence[str], None] = "4f0cb771a4ab"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow an event to have multiple lead sources.
    op.add_column(
        "events",
        sa.Column(
            "source_types",
            sa.ARRAY(sa.String(50)),
            nullable=True,
        ),
    )

    # Store how leads should be handled after the event workflow.
    op.add_column(
        "events",
        sa.Column(
            "lead_handling",
            sa.String(50),
            nullable=True,
        ),
    )

    # Copy the existing single source_type value into the new array column.
    op.execute(
        """
        UPDATE events
        SET source_types = ARRAY[source_type]
        WHERE source_type IS NOT NULL
        """
    )

    # Remove the old single-source column.
    op.drop_column("events", "source_type")


def downgrade() -> None:
    # Restore the original single source column.
    op.add_column(
        "events",
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=True,
        ),
    )

    # Copy the first source back into source_type.
    op.execute(
        """
        UPDATE events
        SET source_type = source_types[1]
        WHERE source_types IS NOT NULL
          AND array_length(source_types, 1) > 0
        """
    )

    op.drop_column("events", "lead_handling")
    op.drop_column("events", "source_types")