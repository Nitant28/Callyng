"""Remove DNC status and campaign counters."""

from alembic import op

revision = "007_remove_dnc"
down_revision = "006_script_configs"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Re-home existing data
    op.execute("""
        UPDATE leads SET status = 'completed', outcome = 'Not_Interested'
        WHERE status = 'dnc';
    """)

    # 2. Recompute campaign counters
    op.execute("""
        UPDATE campaigns c SET
          completed_leads = sub.completed
        FROM (
          SELECT campaign_id, COUNT(*) FILTER (WHERE status='completed')::int AS completed
          FROM leads GROUP BY campaign_id
        ) sub
        WHERE sub.campaign_id = c.id;
    """)

    # 3. Update CHECK constraint
    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;")
    op.execute("""
        ALTER TABLE leads ADD CONSTRAINT leads_status_check
        CHECK (status IN ('pending','calling','completed','failed','callback_scheduled'));
    """)

    # 4. Drop the counter column
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS dnc_leads;")

def downgrade() -> None:
    pass
