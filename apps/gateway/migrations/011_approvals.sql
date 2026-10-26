CREATE TABLE approvals (
 id uuid PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
 tool_id text NOT NULL CHECK (tool_id ~ '^[a-z][a-z0-9_.-]{0,99}$'),
 tool_version text NOT NULL CHECK (tool_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
 arguments_digest text NOT NULL CHECK (arguments_digest ~ '^[0-9a-f]{64}$'),
 policy_digest text NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
 policy_snapshot jsonb NOT NULL,
 requested_by text NOT NULL REFERENCES principals(id),
 status text NOT NULL CHECK (status IN ('pending','approved','rejected','expired','invalidated','consumed')),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 decided_at timestamptz,
 decided_by text REFERENCES principals(id),
 consumed_at timestamptz,
 CHECK (expires_at > created_at),
 CHECK (expires_at <= created_at + interval '24 hours'),
 CHECK (status NOT IN ('approved','rejected','consumed') OR (decided_at IS NOT NULL AND decided_by IS NOT NULL)),
 CHECK (status NOT IN ('pending','expired','invalidated') OR (decided_at IS NULL AND decided_by IS NULL)),
 CHECK ((status = 'consumed') = (consumed_at IS NOT NULL))
);
CREATE UNIQUE INDEX one_pending_approval ON approvals(run_id,tool_id,arguments_digest,policy_digest) WHERE status='pending';
CREATE INDEX approvals_run_created ON approvals(run_id,created_at DESC);
CREATE INDEX approvals_status_expires ON approvals(status,expires_at);
INSERT INTO schema_migrations(version) VALUES (11);
