"""Platform n8n workflow registry (inert until resolver release).

Stores workflow routing metadata only. No credentials, no Meta tokens,
no Gemini keys, no Gmail secrets. Runtime follow-up dispatch is unchanged.
"""

from alembic import op

revision = "017_n8n_workflows"
down_revision = "016_merge_whatsapp_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS n8n_workflows (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            webhook_url TEXT NOT NULL,
            description TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(40) NOT NULL DEFAULT 'active',
            last_tested_at TIMESTAMPTZ,
            last_test_status VARCHAR(40),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT n8n_workflows_name_check CHECK (char_length(btrim(name)) > 0),
            CONSTRAINT n8n_workflows_url_check CHECK (char_length(btrim(webhook_url)) > 0),
            CONSTRAINT n8n_workflows_status_check CHECK (status IN ('active', 'inactive')),
            CONSTRAINT n8n_workflows_last_test_status_check CHECK (
                last_test_status IS NULL OR last_test_status IN
                ('untested', 'success', 'failed', 'dry_run_ok', 'ok', 'error')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_n8n_workflows_enabled_created
          ON n8n_workflows (enabled, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_n8n_workflows_enabled_created")
    op.execute("DROP TABLE IF EXISTS n8n_workflows")
