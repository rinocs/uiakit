ALTER TABLE knowledge_base_versions DROP CONSTRAINT IF EXISTS knowledge_base_versions_state_check;
ALTER TABLE knowledge_base_versions ADD CONSTRAINT knowledge_base_versions_state_check
 CHECK (state IN ('active','reindexing','building','ready','failed','superseded'));
ALTER TABLE knowledge_base_versions ADD COLUMN embedding_provider text;
ALTER TABLE knowledge_base_versions ADD COLUMN embedding_model text;
ALTER TABLE knowledge_base_versions ADD COLUMN embedding_version text;
ALTER TABLE knowledge_base_versions ADD COLUMN embedding_dimension integer;
ALTER TABLE knowledge_base_versions ADD COLUMN collection_name text;
ALTER TABLE knowledge_base_versions ADD COLUMN chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0);
ALTER TABLE knowledge_base_versions ADD COLUMN ready_at timestamptz;
ALTER TABLE knowledge_base_versions ADD COLUMN lease_owner text;
ALTER TABLE knowledge_base_versions ADD COLUMN lease_until timestamptz;
ALTER TABLE knowledge_base_versions ADD COLUMN error_code text;
ALTER TABLE knowledge_base_versions ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0);
ALTER TABLE knowledge_base_versions ADD CONSTRAINT knowledge_base_versions_embedding_check CHECK (
 (embedding_provider IS NULL AND embedding_model IS NULL AND embedding_version IS NULL AND embedding_dimension IS NULL)
 OR (embedding_provider IN ('ollama','openai-compatible') AND embedding_model IS NOT NULL
     AND embedding_version IS NOT NULL AND embedding_dimension BETWEEN 1 AND 8192));
CREATE UNIQUE INDEX one_building_kb_version ON knowledge_base_versions(knowledge_base_id) WHERE state='building';
CREATE UNIQUE INDEX one_collection_kb_version ON knowledge_base_versions(collection_name) WHERE collection_name IS NOT NULL;
CREATE INDEX knowledge_base_versions_claim ON knowledge_base_versions(state,lease_until,created_at);
CREATE TABLE vector_cleanup_jobs (
 id uuid PRIMARY KEY,
 document_id uuid NOT NULL UNIQUE,
 knowledge_base_id uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
 chunk_ids text[] NOT NULL CHECK (cardinality(chunk_ids) > 0),
 state text NOT NULL CHECK (state IN ('queued','running','completed','failed')),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 lease_owner text,
 lease_until timestamptz,
 error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vector_cleanup_claim ON vector_cleanup_jobs(state,lease_until,created_at);
INSERT INTO schema_migrations(version) VALUES (9);
