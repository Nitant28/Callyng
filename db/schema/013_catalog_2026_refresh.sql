-- Upgrade legacy cascade model defaults to 2026 catalog refresh.
UPDATE script_configs
   SET cascade_stt_model = 'saaras:v3'
 WHERE cascade_stt_model IN ('saarika:v2.5', 'saarika:v2', 'saaras:v4');

UPDATE script_configs
   SET cascade_tts_model = 'sonic-3.5'
 WHERE cascade_tts_model = 'sonic-3';

UPDATE script_configs
   SET cascade_stt_model = 'nova-3'
 WHERE cascade_stt_model = 'nova-2';

UPDATE script_configs
   SET cascade_tts_model = 'eleven_flash_v2_5'
 WHERE cascade_tts_model IN ('eleven_turbo_v2_5', 'eleven_multilingual_v2');

UPDATE script_configs
   SET cascade_llm_model = 'gemini-3.6-flash'
 WHERE cascade_llm_provider = 'google'
   AND cascade_llm_model IN ('gemini-2.0-flash', 'gemini-2.0-flash-lite');

UPDATE script_configs
   SET cascade_llm_model = 'openai/gpt-oss-120b'
 WHERE cascade_llm_provider = 'groq'
   AND cascade_llm_model IN ('llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768');
