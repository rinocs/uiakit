CREATE TABLE tool_executions (
 id uuid PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
 tool_id text NOT NULL CHECK (tool_id ~ '^[a-z][a-z0-9_.-]{0,99}$'),
 tool_version text NOT NULL CHECK (tool_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
 arguments_digest text NOT NULL CHECK (arguments_digest ~ '^[0-9a-f]{64}$'),
 approval_id uuid REFERENCES approvals(id),
 risk_level text NOT NULL CHECK (risk_level IN ('read_only','write','destructive')),
 idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
 status text NOT NULL CHECK (status IN ('reserved','running','completed','failed','unknown')),
 attempt integer NOT NULL CHECK (attempt BETWEEN 1 AND 3),
 max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 3),
 result jsonb,
 error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 finished_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,idempotency_key),
 CHECK (risk_level = 'read_only' OR (approval_id IS NOT NULL AND max_attempts = 1)),
 CHECK (status NOT IN ('completed','failed','unknown') OR finished_at IS NOT NULL),
 CHECK (status <> 'completed' OR result IS NOT NULL),
 CHECK (status <> 'failed' OR error_code IS NOT NULL),
 CHECK (status <> 'unknown' OR error_code IS NOT NULL)
);
CREATE INDEX tool_executions_run_created ON tool_executions(run_id,created_at DESC);
CREATE INDEX tool_executions_status_updated ON tool_executions(status,updated_at);
INSERT INTO schema_migrations(version) VALUES (12);
