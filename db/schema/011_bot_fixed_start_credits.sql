-- Setup fee per dial + fractional billed minutes (pro-rata per second).
ALTER TABLE bot_configs
  ADD COLUMN IF NOT EXISTS fixed_start_credits NUMERIC(10,4) NOT NULL DEFAULT 0.6000;

ALTER TABLE call_logs
  ALTER COLUMN billed_minutes TYPE NUMERIC(10,4)
  USING billed_minutes::numeric;
