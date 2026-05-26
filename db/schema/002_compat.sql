-- Idempotent compat layer for legacy DBs (no-op on fresh 001_initial installs).

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_call_id VARCHAR(255);
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS call_sid VARCHAR(255);
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS usage_prompt_tokens INTEGER;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS usage_completion_tokens INTEGER;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS usage_total_tokens INTEGER;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS usage_tts_characters INTEGER;

CREATE INDEX IF NOT EXISTS idx_call_logs_live
    ON call_logs (session_call_id)
    WHERE in_progress = TRUE;

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS plivo_hangup_json JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_call_logs_call_sid
    ON call_logs (call_sid)
    WHERE call_sid IS NOT NULL;
