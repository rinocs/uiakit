CREATE TABLE documents (
 id uuid PRIMARY KEY,
 knowledge_base_id uuid NOT NULL REFERENCES knowledge_bases(id),
 uploaded_by text NOT NULL REFERENCES principals(id),
 filename text NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
 title text NOT NULL CHECK (length(title) <= 200),
 mime_type text NOT NULL CHECK (mime_type IN (
   'text/plain','text/markdown','text/html','application/pdf',
   'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
 size_bytes bigint NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 20971520),
 sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
 blob_key text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(knowledge_base_id,sha256)
);
CREATE INDEX documents_kb_created ON documents(knowledge_base_id,created_at);
CREATE TABLE document_jobs (
 id uuid PRIMARY KEY,
 document_id uuid NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
 state text NOT NULL CHECK (state IN ('queued','running','completed','failed','cancelled')),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 error_code text,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX document_jobs_state ON document_jobs(state,created_at);
INSERT INTO schema_migrations(version) VALUES (6);
