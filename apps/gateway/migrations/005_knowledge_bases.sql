CREATE TABLE knowledge_bases (
 id uuid PRIMARY KEY,
 owner_id text NOT NULL REFERENCES principals(id),
 name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
 description text NOT NULL DEFAULT '' CHECK (length(description)<=4000),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 active_version integer NOT NULL DEFAULT 1 CHECK(active_version>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX knowledge_bases_owner ON knowledge_bases(owner_id,created_at);
CREATE TABLE knowledge_base_versions (
 knowledge_base_id uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
 version integer NOT NULL CHECK(version>0),
 state text NOT NULL CHECK(state IN ('active','reindexing','failed')),
 config jsonb NOT NULL CHECK(jsonb_typeof(config)='object' AND octet_length(config::text)<=65536),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(knowledge_base_id,version)
);
CREATE UNIQUE INDEX one_active_kb_version ON knowledge_base_versions(knowledge_base_id) WHERE state='active';
CREATE UNIQUE INDEX one_reindexing_kb_version ON knowledge_base_versions(knowledge_base_id) WHERE state='reindexing';
ALTER TABLE knowledge_bases ADD CONSTRAINT knowledge_bases_active_version_fk
 FOREIGN KEY(id,active_version) REFERENCES knowledge_base_versions(knowledge_base_id,version)
 DEFERRABLE INITIALLY DEFERRED;
INSERT INTO schema_migrations(version) VALUES (5);
