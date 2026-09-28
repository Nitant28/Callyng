"""Campaign/client n8n workflow assignment (nullable FKs onto n8n_workflows)."""

from alembic import op

revision = "018_campaign_n8n_routing"
down_revision = "017_n8n_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE clients
          ADD COLUMN IF NOT EXISTS default_n8n_workflow_id UUID
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_clients_default_n8n_workflow'
          ) THEN
            ALTER TABLE clients
              ADD CONSTRAINT fk_clients_default_n8n_workflow
              FOREIGN KEY (default_n8n_workflow_id)
              REFERENCES n8n_workflows(id)
              ON DELETE RESTRICT;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE campaigns
          ADD COLUMN IF NOT EXISTS n8n_workflow_id UUID
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_campaigns_n8n_workflow'
          ) THEN
            ALTER TABLE campaigns
              ADD CONSTRAINT fk_campaigns_n8n_workflow
              FOREIGN KEY (n8n_workflow_id)
              REFERENCES n8n_workflows(id)
              ON DELETE RESTRICT;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS fk_campaigns_n8n_workflow"
    )
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS n8n_workflow_id")
    op.execute(
        "ALTER TABLE clients DROP CONSTRAINT IF EXISTS fk_clients_default_n8n_workflow"
    )
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS default_n8n_workflow_id")
