-- Campaign budget settlement idempotency (existing DBs).

ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS budget_returned_at TIMESTAMPTZ;
