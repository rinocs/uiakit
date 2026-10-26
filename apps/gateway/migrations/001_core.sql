CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE assistants (
 id uuid PRIMARY KEY, name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
 model text NOT NULL, system_prompt text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE conversations (
 id uuid PRIMARY KEY, assistant_id uuid NOT NULL REFERENCES assistants(id),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE agent_runs (
 id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 idempotency_key text NOT NULL, content text NOT NULL,
 status text NOT NULL CHECK (status IN ('running','completed','failed')),
 events jsonb NOT NULL DEFAULT '[]', created_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz,
 UNIQUE(conversation_id,idempotency_key)
);
CREATE UNIQUE INDEX one_active_run ON agent_runs(conversation_id) WHERE status='running';
CREATE TABLE messages (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
 role text NOT NULL CHECK (role IN ('user','assistant')), content text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(run_id,role)
);
CREATE INDEX messages_history ON messages(conversation_id,sequence);
INSERT INTO schema_migrations(version) VALUES (1);
