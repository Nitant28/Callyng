-- Dev tenant seed (idempotent). Re-run after db-reset.
-- Dev API key (Bearer): aakashvani_dev_key_change_me
-- SHA-256 hash stored below; never commit the raw key.

-- Fixed UUIDs for local testing
-- client:  00000000-0000-4000-8000-000000000001
-- bot:     00000000-0000-4000-8000-000000000002
-- campaign: 00000000-0000-4000-8000-000000000003
-- sandbox bot (sts):      00000000-0000-4000-8000-000000000004
-- sandbox bot (cascaded): 00000000-0000-4000-8000-000000000005
-- sandbox campaign:       00000000-0000-4000-8000-000000000006

INSERT INTO clients (
    id,
    name,
    contact_email,
    industry,
    api_key_hash,
    balance_credits,
    max_concurrent_calls,
    active
) VALUES (
    '00000000-0000-4000-8000-000000000001',
    'Dev Client',
    'dev@localhost',
    'real_estate',
    '2ad32a4b6d6afeb3333c4211d4491053801e7f05bccb77663f11025b3bf5d394',
    10000.00,
    5,
    TRUE
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    api_key_hash = EXCLUDED.api_key_hash,
    balance_credits = EXCLUDED.balance_credits,
    max_concurrent_calls = EXCLUDED.max_concurrent_calls,
    active = EXCLUDED.active;

INSERT INTO bot_configs (
    id,
    client_id,
    name,
    route,
    script_id,
    telephony_number,
    credits_per_minute,
    active
) VALUES (
    '00000000-0000-4000-8000-000000000002',
    '00000000-0000-4000-8000-000000000001',
    'Diya - Pyramid Parkland - Hindi (dev)',
    'sts',
    'pyramid_hi',
    NULL,
    1.49,
    TRUE
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    route = EXCLUDED.route,
    script_id = EXCLUDED.script_id,
    credits_per_minute = EXCLUDED.credits_per_minute,
    active = EXCLUDED.active;

INSERT INTO campaigns (
    id,
    client_id,
    bot_config_id,
    name,
    status,
    budget_credits,
    budget_used_credits,
    max_concurrent_calls,
    calls_per_minute,
    max_attempts,
    retry_delay_minutes
) VALUES (
    '00000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000002',
    'Dev Draft Campaign',
    'draft',
    0,
    0,
    5,
    10,
    3,
    120
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    bot_config_id = EXCLUDED.bot_config_id;

INSERT INTO bot_configs (
    id,
    client_id,
    name,
    route,
    script_id,
    telephony_number,
    credits_per_minute,
    active
) VALUES (
    '00000000-0000-4000-8000-000000000004',
    '00000000-0000-4000-8000-000000000001',
    'CLI Sandbox (STS)',
    'sts',
    'cli_sandbox_sts',
    NULL,
    1.49,
    TRUE
), (
    '00000000-0000-4000-8000-000000000005',
    '00000000-0000-4000-8000-000000000001',
    'CLI Sandbox (Cascaded)',
    'cascaded',
    'cli_sandbox_cascade',
    NULL,
    1.49,
    TRUE
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    route = EXCLUDED.route,
    script_id = EXCLUDED.script_id,
    credits_per_minute = EXCLUDED.credits_per_minute,
    active = EXCLUDED.active;

INSERT INTO campaigns (
    id,
    client_id,
    bot_config_id,
    name,
    status,
    budget_credits,
    budget_used_credits,
    max_concurrent_calls,
    calls_per_minute,
    max_attempts,
    retry_delay_minutes
) VALUES (
    '00000000-0000-4000-8000-000000000006',
    '00000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000004',
    'CLI Test Sandbox',
    'draft',
    500,
    0,
    5,
    10,
    3,
    120
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    bot_config_id = EXCLUDED.bot_config_id,
    budget_credits = EXCLUDED.budget_credits;
