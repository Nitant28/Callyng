-- Cascade: explicit TTS model + per-role settings blobs.

ALTER TABLE script_configs
    ADD COLUMN IF NOT EXISTS cascade_tts_model    TEXT  DEFAULT 'sonic-3',
    ADD COLUMN IF NOT EXISTS cascade_stt_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS cascade_llm_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS cascade_tts_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE script_configs
   SET cascade_tts_model = 'sonic-3'
 WHERE cascade_tts_model IS NULL;

-- Repair rows that stored the Cartesia model name in the voice column (F20).
UPDATE script_configs
   SET cascade_tts_voice = NULL
 WHERE cascade_tts_voice = 'sonic-3';

-- Voice is optional from here on (D3); stop defaulting it to a model name.
ALTER TABLE script_configs
    ALTER COLUMN cascade_tts_voice DROP DEFAULT;
