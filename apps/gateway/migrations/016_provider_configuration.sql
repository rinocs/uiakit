CREATE TABLE provider_configuration (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    revision integer NOT NULL CHECK (revision > 0),
    provider text NOT NULL CHECK (provider IN ('openai-compatible','ollama')),
    base_url text NOT NULL CHECK (length(base_url) BETWEEN 1 AND 2000),
    api_key_ref text NOT NULL DEFAULT '' CHECK (length(api_key_ref) <= 80),
    max_output_tokens integer NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 8192),
    models jsonb NOT NULL CHECK (jsonb_typeof(models) = 'array' AND jsonb_array_length(models) BETWEEN 1 AND 50),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL
);

INSERT INTO schema_migrations(version) VALUES (16);
