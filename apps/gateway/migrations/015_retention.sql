INSERT INTO principals(id) VALUES ('system-retention') ON CONFLICT DO NOTHING;

CREATE TABLE deletion_tombstones (
    id uuid PRIMARY KEY,
    resource_type text NOT NULL CHECK (resource_type IN ('conversation','document','knowledge_base')),
    resource_id uuid NOT NULL,
    deleted_at timestamptz NOT NULL DEFAULT now(),
    deleted_by text NOT NULL REFERENCES principals(id),
    reason text NOT NULL CHECK (reason IN ('manual','retention')),
    UNIQUE (resource_type, resource_id)
);

CREATE INDEX deletion_tombstones_deleted_at ON deletion_tombstones(deleted_at);
INSERT INTO schema_migrations(version) VALUES (15);
