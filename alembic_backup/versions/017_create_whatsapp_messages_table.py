"""create whatsapp messages table

Revision ID: 4f0cb771a4ab
Revises: 016_add_event_id_to_call_logs
"""

from typing import Sequence, Union

from alembic import op


revision: str = "4f0cb771a4ab"
down_revision: Union[str, Sequence[str], None] = "016_add_event_id_to_call_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE whatsapp_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            lead_id UUID NOT NULL,
            phone VARCHAR(20) NOT NULL,
            wa_id VARCHAR(50),

            direction VARCHAR(10) NOT NULL,
            message_type VARCHAR(30) NOT NULL DEFAULT 'text',
            message TEXT NOT NULL,

            whatsapp_message_id VARCHAR(255),

            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT fk_whatsapp_messages_lead_id
                FOREIGN KEY (lead_id)
                REFERENCES leads(id)
                ON DELETE CASCADE,

            CONSTRAINT whatsapp_messages_direction_check
                CHECK (direction IN ('inbound', 'outbound'))
        )
        """
    )

    op.execute(
        """
        CREATE INDEX idx_whatsapp_messages_lead_id
        ON whatsapp_messages (lead_id)
        """
    )

    op.execute(
        """
        CREATE INDEX idx_whatsapp_messages_created_at
        ON whatsapp_messages (created_at)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_whatsapp_messages_created_at"
    )

    op.execute(
        "DROP INDEX IF EXISTS idx_whatsapp_messages_lead_id"
    )

    op.execute(
        """
        DROP TABLE IF EXISTS whatsapp_messages
        """
    )