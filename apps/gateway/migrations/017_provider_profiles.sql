CREATE TABLE provider_profiles (
    id text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{0,31}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    kind text NOT NULL CHECK (kind IN ('openai-compatible','ollama')),
    base_url text NOT NULL CHECK (length(base_url) BETWEEN 1 AND 2000),
    secret_cipher bytea,
    secret_nonce bytea,
    secret_key_version integer,
    secret_ref text NOT NULL DEFAULT '',
    max_output_tokens integer NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 8192),
    revision integer NOT NULL CHECK (revision > 0),
    config_seq bigint NOT NULL CHECK (config_seq > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL,
    CHECK (secret_ref = '' OR secret_ref ~ '^(MODEL_API_KEY|PROVIDER_API_KEY_[A-Z0-9_]{1,63})$'),
    CHECK ((secret_cipher IS NULL) = (secret_nonce IS NULL)),
    CHECK ((secret_cipher IS NULL) = (secret_key_version IS NULL)),
    CHECK (secret_nonce IS NULL OR octet_length(secret_nonce) = 12),
    CHECK (secret_key_version IS NULL OR secret_key_version >= 1),
    CHECK (secret_cipher IS NULL OR octet_length(secret_cipher) BETWEEN 17 AND 4112),
    CHECK (NOT (secret_cipher IS NOT NULL AND secret_ref <> '')),
    CHECK (kind <> 'ollama' OR (secret_cipher IS NULL AND secret_ref = ''))
);

CREATE TABLE provider_profile_models (
    profile_id text NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
    model_id text NOT NULL CHECK (length(model_id) BETWEEN 1 AND 200),
    capabilities text[] NOT NULL DEFAULT '{}'
        CHECK (capabilities <@ ARRAY['tool_calling','structured_output']::text[]),
    context_window integer CHECK (context_window IS NULL OR context_window > 0),
    PRIMARY KEY (profile_id, model_id)
);

CREATE TABLE provider_revision (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    revision bigint NOT NULL CHECK (revision > 0),
    applied_revision bigint NOT NULL DEFAULT 0
);

INSERT INTO provider_profiles
    (id, name, kind, base_url, secret_ref, max_output_tokens, revision, config_seq,
     updated_at, updated_by)
SELECT 'default', 'Default', provider, base_url, api_key_ref, max_output_tokens,
       GREATEST(revision, 1), GREATEST(revision, 1), updated_at, updated_by
FROM provider_configuration WHERE singleton;

INSERT INTO provider_profile_models (profile_id, model_id, capabilities, context_window)
SELECT 'default', model->>'id',
       ARRAY(SELECT jsonb_array_elements_text(COALESCE(model->'capabilities', '[]'::jsonb))),
       NULLIF(model->>'context_window', '')::integer
FROM provider_configuration, jsonb_array_elements(models) AS model
WHERE singleton;

INSERT INTO provider_revision (singleton, revision, applied_revision)
VALUES (true, (SELECT GREATEST(COALESCE(MAX(revision), 1), 1) FROM provider_configuration), 0);

INSERT INTO schema_migrations(version) VALUES (17);
