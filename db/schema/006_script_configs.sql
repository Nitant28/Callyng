-- Dynamic script & post-call configuration (CMS tables).

CREATE TABLE script_configs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    script_id           TEXT NOT NULL,
    route               TEXT NOT NULL CHECK (route IN ('sts', 'cascaded')),

    -- Agent identity (STS / Gemini Live)
    gemini_model        TEXT NOT NULL DEFAULT 'models/gemini-3.1-flash-live-preview',
    gemini_voice        TEXT NOT NULL DEFAULT 'Aoede',
    gemini_language     TEXT NOT NULL DEFAULT 'hi-IN',
    gemini_temperature  NUMERIC(3,2) NOT NULL DEFAULT 0.50,

    -- VAD
    vad_start_sensitivity   TEXT NOT NULL DEFAULT 'HIGH',
    vad_end_sensitivity     TEXT NOT NULL DEFAULT 'LOW',
    vad_silence_duration_ms INT  NOT NULL DEFAULT 800,
    vad_prefix_padding_ms   INT  NOT NULL DEFAULT 300,

    -- Prompts
    system_instruction_template TEXT NOT NULL,
    bootstrap_messages_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    goodbye_markers             JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Cascade specifics
    cascade_stt_provider    TEXT DEFAULT 'sarvam',
    cascade_stt_model       TEXT DEFAULT 'saarika:v2.5',
    cascade_llm_provider    TEXT DEFAULT 'groq',
    cascade_llm_model       TEXT DEFAULT 'llama-3.3-70b-versatile',
    cascade_tts_provider    TEXT DEFAULT 'cartesia',
    cascade_tts_voice       TEXT DEFAULT 'sonic-3',
    cascade_live_tools      JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Post-call schemas
    extraction_schema   JSONB NOT NULL,
    lead_schema         JSONB NOT NULL DEFAULT '{"fields": []}'::jsonb,

    -- Post-call normalization & outcome mapping
    normalization_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome_event_map   JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome_terminal    JSONB NOT NULL DEFAULT '["Interested", "Not_Interested"]'::jsonb,
    outcome_retry       JSONB NOT NULL DEFAULT '["Busy", "Unknown", "Wrong_Requirement"]'::jsonb,
    outcome_callback    JSONB NOT NULL DEFAULT '["Callback_Requested"]'::jsonb,

    -- Metadata
    active              BOOLEAN NOT NULL DEFAULT true,
    version             INT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (client_id, script_id)
);

CREATE TABLE script_config_revisions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    script_config_id    UUID NOT NULL REFERENCES script_configs(id) ON DELETE CASCADE,
    version             INT NOT NULL,
    config_snapshot     JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (script_config_id, version)
);

ALTER TABLE bot_configs
    ADD COLUMN script_config_id UUID REFERENCES script_configs(id) ON DELETE SET NULL;

CREATE INDEX idx_script_configs_client_id ON script_configs (client_id);
CREATE INDEX idx_script_config_revisions_script_config_id ON script_config_revisions (script_config_id);
CREATE INDEX idx_bot_configs_script_config_id ON bot_configs (script_config_id);
