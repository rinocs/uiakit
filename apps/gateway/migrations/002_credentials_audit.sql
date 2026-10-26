CREATE TABLE principals (id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now());
INSERT INTO principals(id) VALUES ('bootstrap-operator');
CREATE TABLE api_credentials (
 id uuid PRIMARY KEY, principal_id text NOT NULL REFERENCES principals(id),
 role text NOT NULL CHECK (role IN ('admin','operator','reader')),
 scopes text[] NOT NULL CHECK (cardinality(scopes)>0),
 key_digest text NOT NULL UNIQUE CHECK (length(key_digest)=64),
 expires_at timestamptz NOT NULL, revoked_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX api_credentials_principal ON api_credentials(principal_id);
ALTER TABLE assistants ADD COLUMN owner_id text NOT NULL DEFAULT 'bootstrap-operator' REFERENCES principals(id);
ALTER TABLE conversations ADD COLUMN owner_id text NOT NULL DEFAULT 'bootstrap-operator' REFERENCES principals(id);
CREATE INDEX assistants_owner ON assistants(owner_id);
CREATE INDEX conversations_owner ON conversations(owner_id);
CREATE TABLE audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor_principal_id text NOT NULL REFERENCES principals(id),
 action text NOT NULL, target_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_actor_time ON audit_events(actor_principal_id,created_at);
INSERT INTO schema_migrations(version) VALUES (2);
