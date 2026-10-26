-- Desired state is durable; runtime application is a separate, retryable step.
CREATE TABLE IF NOT EXISTS plugin_configuration (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
 settings jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(settings)='object' AND octet_length(settings::text)<=4194304),
 updated_by text NOT NULL DEFAULT 'system',
 updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO plugin_configuration(singleton) VALUES(true) ON CONFLICT (singleton) DO NOTHING;
CREATE TABLE IF NOT EXISTS plugin_configuration_audit (
 revision bigint PRIMARY KEY CHECK(revision>1),
 actor_id text NOT NULL,
 changed_plugin_ids text[] NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version) VALUES (4);
