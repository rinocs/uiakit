ALTER TABLE audit_events
 ADD COLUMN target_type text NOT NULL DEFAULT 'resource',
 ADD COLUMN run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
 ADD COLUMN correlation_id uuid,
 ADD COLUMN digest text,
 ADD COLUMN outcome text NOT NULL DEFAULT 'success',
 ADD COLUMN details jsonb NOT NULL DEFAULT '{}'::jsonb,
 ADD COLUMN retention_class text NOT NULL DEFAULT 'security';
ALTER TABLE audit_events ADD CONSTRAINT audit_events_digest_check
 CHECK (digest IS NULL OR digest ~ '^[0-9a-f]{64}$');
CREATE INDEX audit_events_run_id ON audit_events(run_id,id DESC);
CREATE INDEX audit_events_action_time ON audit_events(action,created_at DESC);
CREATE INDEX audit_events_target ON audit_events(target_id,id DESC);
CREATE INDEX audit_events_retention ON audit_events(retention_class,created_at);
-- Keep replayable correlation for audit reads on runs created before this migration.
ALTER TABLE agent_runs ADD COLUMN correlation_id uuid NOT NULL DEFAULT gen_random_uuid();
INSERT INTO schema_migrations(version) VALUES (13);
