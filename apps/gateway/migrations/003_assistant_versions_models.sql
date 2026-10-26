ALTER TABLE assistants ADD COLUMN current_version integer NOT NULL DEFAULT 1 CHECK(current_version>0);
CREATE TABLE assistant_versions (
 assistant_id uuid NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
 version integer NOT NULL CHECK(version>0), config jsonb NOT NULL CHECK(jsonb_typeof(config)='object' AND config ?& ARRAY['id','version','name','model','system_prompt'] AND config->>'id'=assistant_id::text AND (config->>'version')::integer=version),
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(assistant_id,version)
);
INSERT INTO assistant_versions(assistant_id,version,config)
SELECT id,1,jsonb_build_object(
 'id',id::text,'version',1,'name',name,'description','','model',model,'system_prompt',system_prompt,
 'directives','[]'::jsonb,'tools','[]'::jsonb,'skills','[]'::jsonb,'knowledge_base_ids','[]'::jsonb,
 'memory','{"conversation":true,"semantic":false}'::jsonb,
 'limits','{"max_input_chars":64000,"max_output_chars":64000,"duration_seconds":120}'::jsonb,
 'policy','{"require_tool_approval":true}'::jsonb) FROM assistants;
CREATE FUNCTION reject_assistant_version_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'assistant versions are immutable'; END;
$$;
CREATE TRIGGER assistant_versions_immutable BEFORE UPDATE ON assistant_versions
FOR EACH ROW EXECUTE FUNCTION reject_assistant_version_update();
CREATE TABLE model_configurations (
 id text PRIMARY KEY, definition jsonb NOT NULL CHECK(jsonb_typeof(definition)='object' AND definition ? 'id' AND definition->>'id'=id),
 secret_ref text NOT NULL DEFAULT 'env:MODEL_API_KEY', updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE agent_runs ADD COLUMN assistant_id uuid;
ALTER TABLE agent_runs ADD COLUMN assistant_version integer;
ALTER TABLE agent_runs ADD COLUMN assistant_config jsonb;
ALTER TABLE agent_runs ADD COLUMN model_snapshot jsonb;
UPDATE agent_runs r SET assistant_id=c.assistant_id,assistant_version=1,assistant_config=v.config
 FROM conversations c JOIN assistant_versions v ON v.assistant_id=c.assistant_id AND v.version=1
 WHERE r.conversation_id=c.id;
ALTER TABLE agent_runs ALTER COLUMN assistant_id SET NOT NULL;
ALTER TABLE agent_runs ALTER COLUMN assistant_version SET NOT NULL;
ALTER TABLE agent_runs ALTER COLUMN assistant_config SET NOT NULL;
ALTER TABLE agent_runs ADD CONSTRAINT run_assistant_version_fk FOREIGN KEY(assistant_id,assistant_version)
 REFERENCES assistant_versions(assistant_id,version);
INSERT INTO schema_migrations(version) VALUES (3);
