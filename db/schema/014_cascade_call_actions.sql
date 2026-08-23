-- Cascade call actions: transfer + live-tools toggles.

ALTER TABLE script_configs
    ADD COLUMN IF NOT EXISTS transfer_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS transfer_number TEXT,
    ADD COLUMN IF NOT EXISTS live_tools_enabled BOOLEAN NOT NULL DEFAULT false;

-- Keep existing CMS tools working across the deploy.
UPDATE script_configs
   SET live_tools_enabled = true
 WHERE cascade_live_tools IS NOT NULL
   AND cascade_live_tools <> '[]'::jsonb;
