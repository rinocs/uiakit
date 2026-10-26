CREATE TABLE widget_tokens (
    id text PRIMARY KEY,
    token_digest text NOT NULL UNIQUE,
    assistant_id uuid NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    subject text NOT NULL,
    scopes text[] NOT NULL,
    origin text NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL REFERENCES principals(id)
);

CREATE INDEX widget_tokens_active_digest ON widget_tokens(token_digest)
    WHERE revoked_at IS NULL;
CREATE INDEX widget_tokens_conversation ON widget_tokens(conversation_id);

INSERT INTO schema_migrations(version) VALUES (14);
