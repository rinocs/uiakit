ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check
 CHECK (status IN ('queued','running','waiting_approval','completed','failed','cancelled'));
ALTER TABLE agent_runs ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE agent_runs ADD COLUMN cancel_requested_at timestamptz;
CREATE INDEX agent_runs_owner_created ON agent_runs(created_at DESC);
INSERT INTO schema_migrations(version) VALUES (10);
