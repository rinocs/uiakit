CREATE TABLE document_chunks (
 chunk_id text PRIMARY KEY CHECK (chunk_id ~ '^[0-9a-f]{64}$'),
 document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 document_hash text NOT NULL CHECK (document_hash ~ '^[0-9a-f]{64}$'),
 document_version integer NOT NULL DEFAULT 1 CHECK (document_version > 0),
 chunk_index integer NOT NULL CHECK (chunk_index >= 0),
 page integer NOT NULL CHECK (page > 0),
 start_offset integer NOT NULL CHECK (start_offset >= 0),
 end_offset integer NOT NULL CHECK (end_offset > start_offset),
 text text NOT NULL CHECK (length(text) = end_offset - start_offset),
 chunk_size integer NOT NULL CHECK (chunk_size BETWEEN 1 AND 8000),
 overlap integer NOT NULL CHECK (overlap >= 0 AND overlap < chunk_size),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX document_chunks_document ON document_chunks(document_id,document_version,chunk_index);
CREATE INDEX document_chunks_page ON document_chunks(document_id,page,start_offset);
INSERT INTO schema_migrations(version) VALUES (7);
