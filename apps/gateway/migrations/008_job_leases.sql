ALTER TABLE document_jobs ADD COLUMN lease_owner text;
ALTER TABLE document_jobs ADD COLUMN lease_until timestamptz;
ALTER TABLE document_jobs ADD COLUMN dead_lettered_at timestamptz;
CREATE INDEX document_jobs_claim ON document_jobs(state,lease_until,created_at);
INSERT INTO schema_migrations(version) VALUES (8);
