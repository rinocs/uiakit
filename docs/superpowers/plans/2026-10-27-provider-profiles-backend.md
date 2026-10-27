# Provider Profiles and Stored Credentials (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the singleton provider configuration with named provider
profiles whose credentials can be stored encrypted in PostgreSQL, and let an
assistant bind to any profile through a namespaced `profile/model` identifier.

**Architecture:** The gateway owns the public API, RBAC, audit and the
authoritative PostgreSQL state; it encrypts stored credentials and decrypts them
only into the internal control-plane payload. The runtime keeps one adapter per
profile in memory and routes each run by the namespaced model key. Environment
references remain supported per profile.

**Tech Stack:** Go 1.22 + chi + pgx (gateway), Python >= 3.12 + FastAPI/Pydantic
(runtime), PostgreSQL 17, JSON Schema contracts in `packages/api-contract`.

**Spec:** [2026-10-27-provider-credentials-design.md](../specs/2026-10-27-provider-credentials-design.md)

**Scope:** this plan covers the migration, crypto, gateway API, runtime and e2e
work (spec §16, first plan). The console pages are the second plan and depend on
the HTTP surface defined here.

## Project-wide requirements

- No provider credential value may appear in a public response, an audit detail
  or a log line. Public views expose only `secret_source`, `secret_configured`,
  `secret_readable`.
- Public API changes are additive: the legacy `/v1/provider` schemas and status
  codes stay byte-identical (`docs/releases.md` contract gate).
- Every task leaves the tree building and the suite green; compatibility code is
  removed only in the task that replaces its last caller.
- Migrations are forward-only and additive; `provider_configuration` is neither
  read nor written after `017` and is not dropped.
- Error codes are snake_case and emitted through `problem(w, status, code)`.
- `UAI_SECRET_KEY` is resolved with `secretFromEnv` (so `UAI_SECRET_KEY_FILE`
  works) and must decode to exactly 32 bytes; invalid values abort startup with
  `invalid secret configuration`, an absent value disables stored credentials.
- Key material is AES-256-GCM with AAD `provider-credential:v1:<profile_id>`,
  a 12-byte random nonce, and `secret_key_version = 1`.
- Model resolution is exact key first, then the `default/` prefix fallback; never
  the reverse.
- One commit per task, message `feat(provider): <task title>`.

## Review Focus

- A KEK that changed or was removed leaves stored credentials undecryptable: the
  API must answer `secret_unreadable` and keep environment-reference profiles
  serving, never silently drop or downgrade a credential (Task 5).
- A legacy assistant whose model id already contains a slash (`meta-llama/Llama-3`)
  must keep resolving to the default profile after an administrator creates a
  profile with that prefix (Tasks 7 and 9 pin exact-match precedence).
- Two administrators saving two different profiles concurrently must not receive
  a spurious `version_conflict`, while the global revision stays monotonic
  (Task 3).
- Removing a model used by a legacy bare-id assistant must be rejected with
  `model_in_use`, not silently invalidate that assistant (Tasks 3 and 7).
- Credentials outside the contract (4097 bytes, embedded newline, value on an
  Ollama profile, both sources at once) must be rejected before any write
  (Tasks 2 and 5).

---

### Task 1: Migration 017 — profile tables and backfill

**Files:**
- Create: `apps/gateway/migrations/017_provider_profiles.sql`

**Interfaces:**
- Produces: tables `provider_profiles`, `provider_profile_models`,
  `provider_revision` with the columns used by Task 3.
- Produces: profile `default` holding the legacy singleton configuration.

- [ ] **Step 1: Write the migration**

Create the file with exactly this content (DDL from the spec §5, then the
backfill):

```sql
CREATE TABLE provider_profiles (
    id text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{0,31}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    kind text NOT NULL CHECK (kind IN ('openai-compatible','ollama')),
    base_url text NOT NULL CHECK (length(base_url) BETWEEN 1 AND 2000),
    secret_cipher bytea,
    secret_nonce bytea,
    secret_key_version integer,
    secret_ref text NOT NULL DEFAULT '',
    max_output_tokens integer NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 8192),
    revision integer NOT NULL CHECK (revision > 0),
    config_seq bigint NOT NULL CHECK (config_seq > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL,
    CHECK (secret_ref = '' OR secret_ref ~ '^(MODEL_API_KEY|PROVIDER_API_KEY_[A-Z0-9_]{1,63})$'),
    CHECK ((secret_cipher IS NULL) = (secret_nonce IS NULL)),
    CHECK ((secret_cipher IS NULL) = (secret_key_version IS NULL)),
    CHECK (secret_nonce IS NULL OR octet_length(secret_nonce) = 12),
    CHECK (secret_key_version IS NULL OR secret_key_version >= 1),
    CHECK (secret_cipher IS NULL OR octet_length(secret_cipher) BETWEEN 17 AND 4112),
    CHECK (NOT (secret_cipher IS NOT NULL AND secret_ref <> '')),
    CHECK (kind <> 'ollama' OR (secret_cipher IS NULL AND secret_ref = ''))
);

CREATE TABLE provider_profile_models (
    profile_id text NOT NULL REFERENCES provider_profiles(id) ON DELETE CASCADE,
    model_id text NOT NULL CHECK (length(model_id) BETWEEN 1 AND 200),
    capabilities text[] NOT NULL DEFAULT '{}'
        CHECK (capabilities <@ ARRAY['tool_calling','structured_output']::text[]),
    context_window integer CHECK (context_window IS NULL OR context_window > 0),
    PRIMARY KEY (profile_id, model_id)
);

CREATE TABLE provider_revision (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    revision bigint NOT NULL CHECK (revision > 0),
    applied_revision bigint NOT NULL DEFAULT 0
);

INSERT INTO provider_profiles
    (id, name, kind, base_url, secret_ref, max_output_tokens, revision, config_seq,
     updated_at, updated_by)
SELECT 'default', 'Default', provider, base_url, api_key_ref, max_output_tokens,
       GREATEST(revision, 1), GREATEST(revision, 1), updated_at, updated_by
FROM provider_configuration WHERE singleton;

INSERT INTO provider_profile_models (profile_id, model_id, capabilities, context_window)
SELECT 'default', model->>'id',
       ARRAY(SELECT jsonb_array_elements_text(COALESCE(model->'capabilities', '[]'::jsonb))),
       NULLIF(model->>'context_window', '')::integer
FROM provider_configuration, jsonb_array_elements(models) AS model
WHERE singleton;

INSERT INTO provider_revision (singleton, revision, applied_revision)
VALUES (true, (SELECT GREATEST(COALESCE(MAX(revision), 1), 1) FROM provider_configuration), 0);

INSERT INTO schema_migrations(version) VALUES (17);
```

- [ ] **Step 2: Verify the fresh apply and the backfill**

```bash
docker run --rm -d --name uai-mig-test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_USER=uai -e POSTGRES_DB=uai -p 55433:5432 postgres:17.6-alpine
sleep 5
for f in apps/gateway/migrations/0{01,02,03,04,05,06,07,08,09,10,11,12,13,14,15,16}_*.sql; do
  docker exec -i uai-mig-test psql -U uai -d uai -v ON_ERROR_STOP=1 -q < "$f"
done
docker exec -i uai-mig-test psql -U uai -d uai -v ON_ERROR_STOP=1 -q <<'SQL'
INSERT INTO provider_configuration
  (singleton, revision, provider, base_url, api_key_ref, max_output_tokens, models, updated_by)
VALUES (true, 3, 'openai-compatible', 'https://api.example.com/v1',
        'PROVIDER_API_KEY_TEAM', 512,
        '[{"id":"alpha","capabilities":[]},{"id":"beta","capabilities":["tool_calling"],"context_window":8192}]',
        'boot');
SQL
docker exec -i uai-mig-test psql -U uai -d uai -v ON_ERROR_STOP=1 -q < apps/gateway/migrations/017_provider_profiles.sql
docker exec -i uai-mig-test psql -U uai -d uai -Atc \
  "SELECT id||'|'||kind||'|'||base_url||'|'||secret_ref||'|'||revision||'|'||config_seq FROM provider_profiles"
docker exec -i uai-mig-test psql -U uai -d uai -Atc \
  "SELECT profile_id||'|'||model_id||'|'||array_length(capabilities,1)||'|'||COALESCE(context_window,0) FROM provider_profile_models ORDER BY model_id"
docker exec -i uai-mig-test psql -U uai -d uai -Atc "SELECT revision,applied_revision FROM provider_revision"
docker exec -i uai-mig-test psql -U uai -d uai -Atc "SELECT max(version) FROM schema_migrations"
docker rm -f uai-mig-test
```

Expected output, in order: `default|openai-compatible|https://api.example.com/v1|PROVIDER_API_KEY_TEAM|3|3`;
then `default|alpha||0` and `default|beta|1|8192` (Postgres reports the length of
an empty array as NULL, so alpha's capability column is blank; beta carries one
capability); then `3|0`; then `17`.

- [ ] **Step 3: Commit**

```bash
git add apps/gateway/migrations/017_provider_profiles.sql
git commit -m "feat(provider): add profile tables and backfill the default profile"
```

---

### Task 2: Credential encryption box

**Files:**
- Create: `apps/gateway/provider_secrets.go`
- Test: `apps/gateway/provider_secrets_test.go`

**Interfaces:**
- Produces: `newSecretBox(encoded string) (*secretBox, error)` — `""` returns
  `(nil, nil)`; a non-empty value must be base64-std, 32 bytes, else
  `errSecretConfiguration`.
- Produces: `(*secretBox).seal(profileID, plaintext string) (cipher, nonce []byte, err error)`.
- Produces: `(*secretBox).open(profileID string, cipher, nonce []byte, version int) (string, error)`.
- Produces: `const providerSecretKeyVersion = 1`, `const maxProviderSecretBytes = 4096`,
  errors `errSecretKeyUnavailable`, `errSecretUnreadable`, `errSecretValueInvalid`.

- [ ] **Step 1: Write the failing test**

`apps/gateway/provider_secrets_test.go`:

```go
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"testing"
)

func testBox(t *testing.T) *secretBox {
	t.Helper()
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		t.Fatal(err)
	}
	box, err := newSecretBox(base64.StdEncoding.EncodeToString(key))
	if err != nil || box == nil {
		t.Fatalf("box: %v", err)
	}
	return box
}

func TestSecretBoxRoundTripAndBinding(t *testing.T) {
	box := testBox(t)
	cipher, nonce, err := box.seal("openai", "sk-test-value")
	if err != nil || len(nonce) != 12 || len(cipher) != len("sk-test-value")+16 {
		t.Fatalf("seal: %v nonce=%d cipher=%d", err, len(nonce), len(cipher))
	}
	plain, err := box.open("openai", cipher, nonce, providerSecretKeyVersion)
	if err != nil || plain != "sk-test-value" {
		t.Fatalf("open: %q %v", plain, err)
	}
	if _, err := box.open("other", cipher, nonce, providerSecretKeyVersion); !errors.Is(err, errSecretUnreadable) {
		t.Fatalf("profile binding: %v", err)
	}
	tampered := bytes.Clone(cipher)
	tampered[len(tampered)-1] ^= 0x01
	if _, err := box.open("openai", tampered, nonce, providerSecretKeyVersion); !errors.Is(err, errSecretUnreadable) {
		t.Fatalf("tamper: %v", err)
	}
	if _, err := box.open("openai", cipher, nonce, 2); !errors.Is(err, errSecretUnreadable) {
		t.Fatalf("version: %v", err)
	}
}

func TestSecretBoxConfiguration(t *testing.T) {
	if box, err := newSecretBox(""); box != nil || err != nil {
		t.Fatalf("absent key: %v", err)
	}
	for _, value := range []string{"not-base64!", base64.StdEncoding.EncodeToString(make([]byte, 31))} {
		if _, err := newSecretBox(value); !errors.Is(err, errSecretConfiguration) {
			t.Fatalf("invalid key %q: %v", value, err)
		}
	}
	if _, _, err := (*secretBox)(nil).seal("openai", "value"); !errors.Is(err, errSecretKeyUnavailable) {
		t.Fatalf("nil box: %v", err)
	}
}

func TestSecretBoxRejectsOutOfContractValues(t *testing.T) {
	box := testBox(t)
	for _, value := range []string{"", "line\nbreak", "carriage\rreturn", "nul\x00byte", string(make([]byte, 4097))} {
		if _, _, err := box.seal("openai", value); !errors.Is(err, errSecretValueInvalid) {
			t.Fatalf("value %.20q: %v", value, err)
		}
	}
	cipher, nonce, err := box.seal("openai", "first")
	if err != nil {
		t.Fatal(err)
	}
	second, secondNonce, err := box.seal("openai", "first")
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Equal(nonce, secondNonce) || bytes.Equal(cipher, second) {
		t.Fatal("nonce reuse")
	}
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/gateway && go test ./ -run 'TestSecretBox' -count=1
```

Expected: build failure `undefined: secretBox` (a failing run).

- [ ] **Step 3: Implement `provider_secrets.go`**

Declare the errors and constants from Interfaces. `newSecretBox` decodes with
`base64.StdEncoding`, requires exactly 32 bytes, and builds an AES-GCM cipher
through `cipher.NewGCM`. `seal` validates the plaintext (1..4096 bytes, no `\r`,
`\n`, `\0`) then encrypts with AAD
`[]byte("provider-credential:v1:" + profileID)` and a 12-byte nonce from
`io.ReadFull(rand.Reader, nonce)`. `open` returns `errSecretUnreadable` for any
version other than `providerSecretKeyVersion` or any AEAD failure, so a missing
or rotated KEK can never surface as a silent empty credential. A nil box returns
`errSecretKeyUnavailable` from `seal` and `errSecretUnreadable` from `open`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/gateway && go test ./ -run 'TestSecretBox' -count=1 && go vet ./...
```

Expected: `ok  universal-ai-kit/gateway` and no vet output.

- [ ] **Step 5: Commit**

```bash
git add apps/gateway/provider_secrets.go apps/gateway/provider_secrets_test.go
git commit -m "feat(provider): add AES-GCM credential box"
```

---

### Task 3: Profile store, revision counters and boot key wiring

**Files:**
- Modify: `apps/gateway/types.go:149-153` (`ProviderStore` interface: add methods, keep the two legacy ones)
- Modify: `apps/gateway/provider_store.go` (add profile methods, implement the alias rule)
- Modify: `apps/gateway/server.go:24-34` (`Config`), `apps/gateway/main.go` (load `UAI_SECRET_KEY`)
- Modify: `apps/gateway/provider_test.go` (the fake store must implement the new interface methods so the package compiles; Task 4 replaces it)
- Test: `apps/gateway/provider_store_test.go`

**Interfaces:**
- Consumes: `secretBox` from Task 2.
- Produces: `type ProviderProfile struct { ID, Name, Provider, BaseURL, SecretRef string; SecretCipher, SecretNonce []byte; SecretKeyVersion, MaxOutputTokens, Revision int; ConfigSeq int64; Models []ProviderModel }`
- Produces: `type ProviderSecret struct { Source string; Cipher, Nonce []byte; KeyVersion int; Ref string }` with `Source` in `none|stored|env`.
- Produces interface methods:
  `ProviderProfiles(context.Context) ([]ProviderProfile, error)`,
  `ProviderProfile(context.Context, string) (ProviderProfile, error)`,
  `CreateProviderProfile(context.Context, ProviderProfile) (ProviderProfile, error)`,
  `UpdateProviderProfile(context.Context, string, int, ProviderProfile) (ProviderProfile, error)`,
  `DeleteProviderProfile(context.Context, string) error`,
  `SetProviderSecret(context.Context, string, ProviderSecret) (ProviderProfile, error)`,
  `ProviderAppliedRevision(context.Context) (int64, error)`,
  `MarkProviderApplied(context.Context, int64) error`.
- Produces: `Config.SecretKey *secretBox`.
- Keeps: `ProviderConfiguration`/`SaveProviderConfiguration` so `provider.go` keeps
  building; Task 6 removes them.

- [ ] **Step 1: Write the failing test**

`apps/gateway/provider_store_test.go`, skipped when `UAI_TEST_DATABASE_URL` is
unset (`providerTestStore(t)` calls `OpenStore`, truncates
`provider_profile_models`, `provider_profiles` and `assistants`, and resets the
singleton with `UPDATE provider_revision SET revision=1, applied_revision=0` so the
counter is deterministic without ever removing the row):

```go
func TestProviderStoreProfiles(t *testing.T) {
	store := providerTestStore(t)
	ctx := context.Background()

	created, err := store.CreateProviderProfile(ctx, ProviderProfile{
		ID: "openai", Name: "OpenAI", Provider: "openai-compatible",
		BaseURL: "https://api.example.com/v1", MaxOutputTokens: 512,
		Models: []ProviderModel{{ID: "alpha"}, {ID: "beta", Capabilities: []string{"tool_calling"}}},
	})
	if err != nil || created.Revision != 1 || created.ConfigSeq != 1 {
		t.Fatalf("create: %+v %v", created, err)
	}
	if _, err := store.CreateProviderProfile(ctx, created); !errors.Is(err, ErrConflict) {
		t.Fatalf("duplicate id: %v", err)
	}

	created.Name = "OpenAI EU"
	if _, err := store.UpdateProviderProfile(ctx, "openai", 0, created); !errors.Is(err, ErrConflict) {
		t.Fatalf("stale expected: %v", err)
	}
	updated, err := store.UpdateProviderProfile(ctx, "openai", 1, created)
	if err != nil || updated.Revision != 2 || updated.ConfigSeq != 2 {
		t.Fatalf("update: %+v %v", updated, err)
	}

	// A write to another profile must not conflict with the first one.
	other, err := store.CreateProviderProfile(ctx, ProviderProfile{
		ID: "local", Name: "Local", Provider: "ollama",
		BaseURL: "http://ollama:11434", MaxOutputTokens: 256,
		Models: []ProviderModel{{ID: "llama3.2:3b"}},
	})
	if err != nil || other.ConfigSeq != 3 {
		t.Fatalf("second profile: %+v %v", other, err)
	}

	stored, err := store.SetProviderSecret(ctx, "openai", ProviderSecret{
		Source: "stored", Cipher: bytes.Repeat([]byte{7}, 32), Nonce: bytes.Repeat([]byte{1}, 12), KeyVersion: 1,
	})
	if err != nil || len(stored.SecretCipher) == 0 || stored.SecretRef != "" || stored.Revision != 3 {
		t.Fatalf("stored secret: %+v %v", stored, err)
	}
	envRef, err := store.SetProviderSecret(ctx, "openai", ProviderSecret{Source: "env", Ref: "MODEL_API_KEY"})
	if err != nil || envRef.SecretCipher != nil || envRef.SecretRef != "MODEL_API_KEY" {
		t.Fatalf("env secret: %+v %v", envRef, err)
	}

	if applied, err := store.ProviderAppliedRevision(ctx); err != nil || applied != 0 {
		t.Fatalf("applied: %d %v", applied, err)
	}
	if err := store.MarkProviderApplied(ctx, 6); err != nil {
		t.Fatal(err)
	}
	if err := store.MarkProviderApplied(ctx, 2); err != nil {
		t.Fatal(err)
	}
	if applied, _ := store.ProviderAppliedRevision(ctx); applied != 6 {
		t.Fatalf("applied regressed: %d", applied)
	}

	if _, err := store.pool.Exec(ctx,
		`INSERT INTO assistants(id,name,model,system_prompt) VALUES
		 (gen_random_uuid(),'legacy','beta','p'),(gen_random_uuid(),'current','openai/alpha','p')`); err != nil {
		t.Fatal(err)
	}
	for key, want := range map[string]int{
		"openai/alpha": 1, "default/beta": 1, "openai/beta": 0, "local/alpha": 0,
	} {
		if count, err := store.AssistantsUsingModel(ctx, key); err != nil || count != want {
			t.Fatalf("%s: %d %v", key, count, err)
		}
	}

	if err := store.DeleteProviderProfile(ctx, "local"); err != nil {
		t.Fatalf("delete: %v", err)
	}
	if _, err := store.ProviderProfile(ctx, "local"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("deleted profile: %v", err)
	}
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker run --rm -d --name uai-store-test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_USER=uai -e POSTGRES_DB=uai -p 55432:5432 postgres:17.6-alpine
sleep 5
cd apps/gateway && UAI_TEST_DATABASE_URL=postgres://uai:test@127.0.0.1:55432/uai \
  go test ./ -run TestProviderStoreProfiles -count=1
```

Expected: build failure (`undefined: providerTestStore`, missing methods).

- [ ] **Step 3: Implement the store and the boot secret**

Every write runs in one transaction that first locks the singleton
(`SELECT revision FROM provider_revision WHERE singleton FOR UPDATE`), bumps it,
and stores the new value in `provider_profiles.config_seq`. `CreateProviderProfile`
returns `ErrConflict` on a duplicate id; `UpdateProviderProfile` compares the
stored `revision` with `expected` (`ErrConflict` otherwise), then replaces the
model rows; `DeleteProviderProfile` bumps the global revision and deletes the row;
`SetProviderSecret` maps `Source` onto the columns (`stored` → cipher/nonce/version
and empty ref, `env` → ref and three NULLs, `none` → all empty) and bumps the
profile revision; `MarkProviderApplied` is
`UPDATE provider_revision SET applied_revision=$1 WHERE singleton AND applied_revision<$1`.

Each mutation records an audit row in the same transaction
(`recordAudit(ctx, tx, AuditRecord{...})`): actions `provider.created`,
`provider.updated`, `provider.deleted`, `provider.secret.set`,
`provider.secret.clear`, `TargetType: "provider"`, `TargetID: profile.ID`,
details limited to `profile_id`, `revision`, `kind`, `base_url`, `models`,
`secret_source`.

`AssistantsUsingModel(key)` counts `model=$1`, plus the bare alias for keys under
the default profile (legacy versions store the model without a prefix):

```go
func (s *PostgresStore) AssistantsUsingModel(ctx context.Context, model string) (int, error) {
	alias := ""
	if strings.HasPrefix(model, "default/") {
		alias = strings.TrimPrefix(model, "default/")
	}
	var count int
	err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM assistants WHERE model=$1 OR ($2<>'' AND model=$2)`,
		model, alias).Scan(&count)
	return count, err
}
```

The alias must be computed explicitly: calling `strings.TrimPrefix` inline would
return the key unchanged for every other profile and count unrelated assistants.

In `main.go`, after the existing `DATABASE_URL` boot secret:

```go
secretKey, e := secretFromEnv("UAI_SECRET_KEY")
if e != nil {
    log.Fatal("invalid secret configuration")
}
box, e := newSecretBox(secretKey)
if e != nil {
    log.Fatal("invalid secret configuration")
}
```

and add `SecretKey: box` to the `Config` literal in `main.go`.

- [ ] **Step 4: Run the test to verify it passes, then stop the container**

```bash
cd apps/gateway && UAI_TEST_DATABASE_URL=postgres://uai:test@127.0.0.1:55432/uai \
  go test ./ -run TestProviderStoreProfiles -count=1 && go test ./ -count=1 && go vet ./...
docker rm -f uai-store-test
```

Expected: `ok  universal-ai-kit/gateway` twice (the guarded test is skipped in
the second run), no vet output.

- [ ] **Step 5: Commit**

```bash
git add apps/gateway/provider_store.go apps/gateway/provider_store_test.go \
  apps/gateway/types.go apps/gateway/server.go apps/gateway/main.go
git commit -m "feat(provider): persist profiles, secrets and revision counters"
```

---

### Task 4: Profile CRUD API and plane push

**Files:**
- Modify: `apps/gateway/provider.go`
- Test: `apps/gateway/provider_test.go` (replace the fake store, keep the existing scenarios)

**Interfaces:**
- Consumes: Task 3 store methods and `Config.SecretKey`.
- Produces: `ProviderProfileView`, `ProviderProfileInput`, `ProviderProfileCreate`.
- Produces handlers `providers`, `createProviderProfile`, `providerProfile`, `updateProviderProfile`, `deleteProviderProfile`.
- Produces validation `validProviderProfileInput(id, name, kind, baseURL string, maxTokens int, models []ProviderModel) bool` and `providerProfileView(profile ProviderProfile, applied int64) ProviderProfileView`.
- Produces plane types and functions: `providerRuntimePlane{Revision int64; Profiles []providerRuntimeProfile}`, `providerRuntimeProfile{ID, Name, Provider, BaseURL, APIKey, APIKeyRef string; MaxOutputTokens int; Models []ProviderModel}`, `runtimePlane(context.Context) (providerRuntimePlane, error)`, `applyProviderPlane(context.Context) (int64, error)`.
- Produces routes: `GET /v1/providers`, `POST /v1/providers`, `GET|PUT|DELETE /v1/providers/{id}`.

- [ ] **Step 1: Write the failing tests**

Rewrite the fake store in `provider_test.go` as `providerPlaneStore` (fields
`profiles []ProviderProfile`, `applied int64`, `inUse map[string]int`,
`synced []ModelDefinition`) implementing the whole `ProviderStore` interface with
the Task 3 semantics, and keep the existing runtime fake.

Tests (assertions listed; authenticate as in the existing file):

- `TestProviderListRequiresReadScope`: reader without `providers:read` → 403.
- `TestProviderCreateReturnsViewWithoutCredentials`: POST
  `{"id":"openai","name":"OpenAI","provider":"openai-compatible","base_url":"https://api.example.com/v1","max_output_tokens":512,"models":[{"id":"alpha","capabilities":[],"context_window":null}]}`
  → 200 with `revision:1`, `secret_source:"none"`, `secret_configured:false`;
  the raw JSON has none of `api_key`, `api_key_ref`, `secret_cipher`,
  `secret_nonce`.
- `TestProviderCreateRejectsInvalidInput`: 422 `invalid_profile_id` (`"Bad Id"`),
  `invalid_configuration` (`max_output_tokens:0`), `duplicate_model_id`,
  `invalid_provider_url` (`http://user:pw@host/v1`), `too_many_profiles` (21st).
- `TestProviderUpdateRequiresIfMatch`: no `If-Match` → 428; stale → 412
  `version_conflict`; current → 200 with `revision:2`.
- `TestProviderRemovedModelInUse`: fake reports `inUse["default/beta"]=1`; PUT
  removing `beta` from the `default` profile → 409 `model_in_use`.
- `TestProviderDeleteBlocksProfileInUse`: fake reports `inUse["openai/alpha"]=1`
  → DELETE → 409 `profile_in_use`; after clearing → 204 and GET → 404 `not_found`.
- `TestProviderViewNeverExposesStoredCipher`: profile with `SecretCipher`/`SecretNonce`
  → GET shows `secret_source:"stored"`, `secret_readable:true`, and the raw body
  contains neither `cipher` nor the base64 of those bytes.
- `TestRuntimePlaneSendsPlaintextOnlyInternally`: two profiles, one stored
  (`sk-live-123`) and one `api_key_ref:"MODEL_API_KEY"`; `runtimePlane` →
  `Profiles[0].APIKey == "sk-live-123"`, `Profiles[1].APIKey == "" && APIKeyRef == "MODEL_API_KEY"`,
  `Revision` equals the fake global revision; `GET /v1/providers` does not contain
  `sk-live-123`.
- `TestApplyPushesAndReportsApplied`: after a successful create the runtime fake
  received a plane whose `revision` equals the store global revision, and the
  response body has `applied:true`.
- `TestApplyFailureReturnsPending`: runtime `/apply` returns 422 → write answers
  502 `provider_pending` and the row stays saved.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/gateway && go test ./ -run 'TestProvider|TestRuntimePlane|TestApply' -count=1
```

Expected: build failure or 404 on the new routes.

- [ ] **Step 3: Implement types, validation, handlers and the plane**

`validProviderProfileInput` enforces the id pattern
`^[a-z0-9][a-z0-9-]{0,31}$`, a trimmed `name` of 1–80 chars equal to the input,
a known kind, `validProviderBaseURL`, `1 <= maxTokens <= 8192`, 1–50 models with
`validModelID`, uniqueness, `len(id)+1+len(model.ID) <= 200`, and the capability
rules already present (`ollama` forbids capabilities). Error mapping:
`invalid_profile_id`, `invalid_configuration`, `duplicate_model_id`,
`invalid_provider_url`, `too_many_profiles`, `invalid_model_id`.

`providerProfileView` sets `Applied: applied >= profile.ConfigSeq`, `Managed: true`,
`SecretSource` from the row, `SecretConfigured: cipher != nil || ref != ""`,
`SecretReadable: cipher == nil || (config.SecretKey != nil && version == providerSecretKeyVersion)`.

`runtimePlane` reads every profile, decrypts stored ciphers through
`config.SecretKey.open` (mapping `errSecretUnreadable` → 502 `secret_unreadable`)
and fills exactly one of `APIKey`/`APIKeyRef`. `applyProviderPlane` posts the
plane to `/internal/v1/provider/apply`; non-200 maps to `provider_pending`; on
200 it calls `syncRuntimeModels` and returns the plane revision.

Delete iterates the profile models and calls
`AssistantsUsingModel(id+"/"+model.ID)`, answering 409 `profile_in_use` on the
first non-zero count. Every write calls `applyProviderPlane` and reports
`applied` from the returned revision; reads report `applied` from
`ProviderAppliedRevision`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/gateway && go test ./ -run 'TestProvider|TestDesiredPlane|TestApply' -count=1 && go vet ./...
```

Expected: `ok  universal-ai-kit/gateway`.

- [ ] **Step 5: Commit**

```bash
git add apps/gateway/provider.go apps/gateway/provider_test.go
git commit -m "feat(provider): add profile CRUD API and plane push"
```

---

### Task 5: Credential endpoints and profile discovery

**Files:**
- Modify: `apps/gateway/provider.go`
- Modify: `apps/runtime/uai_runtime/provider_control.py` (`ProviderDiscoveryConfig.api_key`)
- Modify: `packages/api-contract/internal.openapi.json` (regenerated)
- Test: `apps/gateway/provider_test.go`, `apps/runtime/tests/test_provider_control.py`

**Interfaces:**
- Consumes: Task 2 box, Task 3 `SetProviderSecret`, Task 4 `runtimePlane`.
- Produces: `ProviderSecretInput{Source, Value, Ref string}` and handlers `setProviderCredential`, `clearProviderCredential`, `discoverProfileModels`.
- Produces routes: `PUT|DELETE /v1/providers/{id}/secret`, `POST /v1/providers/{id}/models/discovery`.
- Produces: `ProviderDiscoveryConfig.api_key: str = ''`; `discover_models` uses it
  when non-empty, otherwise resolves `api_key_ref`. The runtime must accept this
  field in the same task, because the gateway starts sending it here and
  `ProviderDiscoveryConfig` forbids unknown fields.

- [ ] **Step 1: Write the failing tests**

- `TestProviderSecretStoredRoundTrip`: PUT `{"source":"stored","value":"sk-live-123"}`
  → 200 with `secret_source:"stored"`, `secret_configured:true`; the fake store
  holds a non-empty cipher and an empty ref; the response body does not contain
  `sk-live-123`.
- `TestProviderSecretRequiresKey`: `Config.SecretKey` nil → stored value → 503
  `secret_key_unavailable`; `{"source":"env","ref":"MODEL_API_KEY"}` still
  succeeds with `secret_source:"env"`.
- `TestProviderSecretValidation`: 422 `secret_value_invalid` for an empty value, a
  `\n` value and a 4097-byte value; `invalid_api_key_ref` for
  `{"source":"env","ref":"INTERNAL_API_KEY"}`; `api_key_ref_not_supported` for a
  stored value on an `ollama` profile; `invalid_configuration` when both value and
  ref are sent.
- `TestProviderSecretUnreadableVersion`: store returns `SecretKeyVersion: 2` → the
  write answers 502 `secret_unreadable`.
- `TestProviderDiscoveryUsesStoredSecret`: fake store holds an encrypted value;
  discovery → runtime fake receives `api_key == "sk-live-123"` and `api_key_ref == ""`.
- `TestProviderDiscoveryEnvRef`: profile with `SecretRef:"PROVIDER_API_KEY_TEAM"` →
  runtime receives that ref and an empty `api_key`.
- `test_discovery_prefers_inline_api_key` (pytest): a `MockTransport` handler
  records the `Authorization` header; a discovery config with
  `api_key='sk-inline'` and `api_key_ref='MODEL_API_KEY'` sends
  `Bearer sk-inline`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/gateway && go test ./ -run 'TestProviderSecret|TestProviderDiscovery' -count=1
```

Expected: 404 from the missing routes.

- [ ] **Step 3: Implement the endpoints**

`setProviderCredential` loads the profile (404 `not_found`), rejects credentials
on `ollama` (`api_key_ref_not_supported`), requires exactly one of `stored`/`env`,
seals stored values with `box.seal(profile.ID, value)`, calls
`store.SetProviderSecret`, applies the plane, and maps `errSecretKeyUnavailable`
→ 503, `errSecretUnreadable` → 502, `errSecretValueInvalid` → 422
`secret_value_invalid`. `clearProviderCredential` writes `Source:"none"`. Both
respond `{"secret_source": "...", "secret_configured": bool}` and never echo the
value.

`discoverProfileModels` loads the profile, decrypts a stored cipher, and posts
`{provider, base_url, api_key}` to `/internal/v1/provider/models`; environment
references post `api_key_ref`. Add `api_key: str = ''` to
`ProviderDiscoveryConfig`, keep `_valid_base_url`/`_valid_secret_ref` checks, and
have `discover_models` send `Authorization: Bearer <api_key>` when it is
non-empty, falling back to `resolve_api_key(config.api_key_ref)` otherwise.
Regenerate the internal contract after the model change:

```bash
cd apps/runtime && python -c "
import json
from uai_runtime.app import create_app
from uai_runtime.provider import OpenAIProvider
print(json.dumps(create_app('internal-secret', OpenAIProvider('http://provider/v1', '')).openapi(),
                 indent=2, sort_keys=True))" > /tmp/internal.openapi.json
cp /tmp/internal.openapi.json packages/api-contract/internal.openapi.json
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/gateway && go test ./ -count=1 && go vet ./... && cd ../runtime && python -m pytest tests/ -q
```

Expected: `ok  universal-ai-kit/gateway`.

- [ ] **Step 5: Commit**

```bash
git add apps/gateway/provider.go apps/gateway/provider_test.go
git commit -m "feat(provider): accept and rotate stored credentials"
```

---

### Task 6: Internal desired/applied and legacy provider aliases

**Files:**
- Modify: `apps/gateway/provider.go` (internal handlers, legacy handlers, unmanaged fallback)
- Modify: `apps/gateway/provider_store.go`, `apps/gateway/types.go` (remove the two legacy store methods)
- Test: `apps/gateway/provider_test.go`

**Interfaces:**
- Consumes: Task 3 store, Task 4 plane.
- Produces: `runtimeProviderState{Revision int64; Profiles []runtimeProviderProfile}` (no secret fields) and `fetchRuntimeProviderState` over it.
- Produces: internal `GET /internal/v1/provider/desired` returning `providerRuntimePlane`.
- Produces: legacy `GET/PUT /v1/provider`, `POST /v1/provider/models` over the `default` profile with the unchanged `ProviderView` schema.

- [ ] **Step 1: Write the failing tests**

- `TestDesiredReturnsThePlane`: `GET /internal/v1/provider/desired` (internal
  bearer) → 200 with `revision` and `profiles[].api_key`; without the bearer → 401;
  when no profile exists → 404 `not_configured`.
- `TestAppliedMarksRevision`: `POST /internal/v1/provider/applied {"revision":4}`
  calls `MarkProviderApplied(4)` then `SyncModels`; a later `GET /v1/providers`
  reports `applied:true` for a profile with `config_seq <= 4` and `false` above it.
- `TestLegacyProviderViewSchema`: with a `default` profile, `GET /v1/provider`
  returns exactly `revision,managed,applied,provider,base_url,api_key_ref,api_key_configured,max_output_tokens,models`
  and `ETag: "<profile revision>"`.
- `TestLegacyProviderUpdateMapsToDefault`: the legacy PUT updates the `default`
  profile and never changes its id or kind.
- `TestLegacyProviderWhenUnmanaged`: no profile, runtime reports an environment
  default → legacy GET 200 `managed:false` with runtime values; `GET /v1/providers`
  returns one synthetic profile `{id:"default", managed:false}` built from the
  runtime state.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/gateway && go test ./ -run 'TestDesired|TestApplied|TestLegacyProvider' -count=1
```

Expected: failures on the old payload shape.

- [ ] **Step 3: Implement the internal and legacy surfaces**

Point `/desired` at `runtimePlane`, `/applied` at
`MarkProviderApplied` + `syncRuntimeModels`, and change
`fetchRuntimeProviderState` to decode the plane state. Rebuild the legacy
handlers on `ProviderProfile`: GET builds `ProviderView` from `default`
(`Managed:true`, `APIKeyConfigured` from the runtime state profile `default`);
PUT maps `ProviderUpdate` onto `ProviderProfileInput` (creating `default` when
absent) and never rewrites `id`/`kind`; discovery forwards
`provider/base_url/api_key_ref` unchanged. When no profile exists, keep today's
`managed:false` behaviour and add the synthetic `default` entry to
`GET /v1/providers`. Remove the two legacy store methods
(`ProviderConfiguration`, `SaveProviderConfiguration`) from the interface and the
store, keeping the `ProviderConfiguration`/`ProviderView` types: they remain the
legacy API schema.

- [ ] **Step 4: Run the full gateway suite**

```bash
cd apps/gateway && go test -race ./ -count=1 && go vet ./...
```

Expected: `ok  universal-ai-kit/gateway`, no race reports.

- [ ] **Step 5: Commit**

```bash
git add apps/gateway/provider.go apps/gateway/provider_store.go apps/gateway/types.go \
  apps/gateway/provider_test.go
git commit -m "feat(provider): push the profile plane and keep the legacy provider API"
```

---

### Task 7: Namespaced model keys in assistants and the catalog

**Files:**
- Modify: `apps/gateway/models.go` (definition limit, read cap)
- Modify: `apps/gateway/assistant_store.go` (model lookup, `SyncModels` limit)
- Modify: `apps/gateway/provider.go` (`removedModelInUse`)
- Modify: `apps/gateway/provider_store.go`, `apps/gateway/types.go` (`ResolveModelKey`)
- Test: `apps/gateway/assistants_test.go`, `apps/gateway/provider_test.go`, `apps/gateway/provider_store_test.go`

**Interfaces:**
- Consumes: `AssistantsUsingModel` alias rule from Task 3.
- Produces: `ProviderStore.ResolveModelKey(context.Context, string) (string, error)` —
  exact `model_configurations` key first, then `"default/" + model`; returns
  `ErrNotFound` when neither exists.
- Produces: `func resolveModelKey(ctx context.Context, store Store, model string) (string, error)`
  delegating to the store method, used by assistant validation and `removedModelInUse`.
- Produces: `const maxProviderDefinitions = 1000`; `SyncModels` and
  `loadRuntimeModels` accept up to that many, and the runtime catalog read is
  capped at 2 MiB.

- [ ] **Step 1: Write the failing tests**

- `TestAssistantLegacyModelResolves`: catalog holds `default/alpha`; create an
  assistant with `model:"alpha"` → 200 and the stored config keeps `alpha`.
- `TestAssistantModelWithSlashResolvesToDefault`: catalog holds
  `default/meta-llama/Llama-3`; `model:"meta-llama/Llama-3"` → 200.
- `TestAssistantExactKeyBeatsDefaultFallback`: catalog holds `other/alpha` and
  `default/other/alpha`; `model:"other/alpha"` resolves to `other/alpha`, asserted
  through the definition's `provider` value returned by `GET /v1/models`.
- `TestAssistantUnknownModelRejected`: `model:"missing"` → 422 `invalid_model`.
- `TestRemovedModelInUseUsesBareAlias`: fake `AssistantsUsingModel` returns 1 for
  `beta` when asked for `default/beta`; removing `beta` → 409 `model_in_use`.
- `TestSyncModelsAcceptsManyProfiles`: 60 namespaced definitions → nil error; 1001
  → `ErrInvalidConfig`.
- `TestLoadRuntimeModelsRejectsOversizedCatalog`: runtime returns 1001
  definitions → error.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/gateway && go test ./ -run 'TestAssistant|TestRemoved|TestSyncModels|TestLoadRuntimeModels' -count=1
```

Expected: failures on missing keys and limits.

- [ ] **Step 3: Implement the resolution and the limits**

Implement `ProviderStore.ResolveModelKey` in `provider_store.go` with two
`model_configurations` lookups (`SELECT definition FROM model_configurations WHERE
id=$1`, then the `default/`-prefixed key) and return `ErrNotFound` when both miss;
`resolveModelKey` in `models.go` delegates to it. Use it in the assistant
version-creation validation in `assistant_store.go` and in `removedModelInUse`;
for a removed key under `default`, the in-use check must also match the bare
legacy form, which Task 3's `AssistantsUsingModel` already does. Add the
`ResolveModelKey` case to `provider_store_test.go` (exact key, fallback,
missing). Raise `maxProviderDefinitions` to 1000 in `models.go`, mirror it in
`SyncModels`, and raise the catalog read limit from 64 KiB to 2 MiB.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/gateway && go test -race ./ -count=1
```

Expected: `ok  universal-ai-kit/gateway`.

- [ ] **Step 5: Commit**

```bash
git add apps/gateway/models.go apps/gateway/assistant_store.go apps/gateway/provider.go \
  apps/gateway/provider_store.go apps/gateway/types.go \
  apps/gateway/assistants_test.go apps/gateway/provider_test.go apps/gateway/provider_store_test.go
git commit -m "feat(provider): resolve namespaced assistant model keys"
```

---

### Task 8: Public contract and TypeScript SDK

**Files:**
- Modify: `packages/api-contract/public.openapi.json`
- Modify: `packages/sdk-typescript/src/generated.ts` (regenerated), `src/operations.ts`, `src/client.ts`
- Test: `apps/runtime/tests/test_contract.py`

**Interfaces:**
- Consumes: the HTTP surface from Tasks 4–6.
- Produces: SDK resource `client.providers` with `list()`, `create(body)`,
  `get(id)`, `update(id, body, {ifMatch})`, `remove(id)`, `setSecret(id, body)`,
  `clearSecret(id)`, `discoverModels(id)`; `client.provider` keeps its legacy
  methods unchanged.

- [ ] **Step 1: Write the failing contract test**

Add to `apps/runtime/tests/test_contract.py`:

```python
def test_provider_profile_contract_keeps_credentials_write_only():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    schemas = public['components']['schemas']
    props = schemas['ProviderProfile']['properties']
    assert not {'api_key', 'secret_cipher', 'secret_nonce', 'secret_key_version'} & props.keys()
    assert {'secret_source', 'secret_configured', 'secret_readable'} <= props.keys()
    secret = schemas['ProviderSecretInput']['properties']
    assert set(secret) == {'source', 'value', 'ref'}
    assert secret['value']['writeOnly'] is True and secret['ref']['writeOnly'] is True
    assert public['paths']['/v1/providers/{id}/secret']['put']['operationId'] == 'setProviderSecret'
    assert '409' in public['paths']['/v1/providers/{id}']['delete']['responses']
    assert public['paths']['/v1/provider']['get']['operationId'] == 'getProvider'
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/runtime && python -m pytest tests/test_contract.py -q
```

Expected: `KeyError: 'ProviderProfile'`.

- [ ] **Step 3: Extend the contract and regenerate the SDK**

Add the eight paths, the schemas `ProviderProfile`, `ProviderProfileInput`,
`ProviderProfileCreate`, `ProviderProfileList`, `ProviderSecretInput`,
`ProviderSecretView`, and the spec's error codes, leaving `/v1/provider` byte
identical. Then:

```bash
cd packages/sdk-typescript && npm run generate && npm run check:contract
```

Add the eight operations to `src/operations.ts` (`updateProviderProfile` with
`requiresIfMatch: true`) and the `ProvidersResource` class to `src/client.ts`,
mirroring `ProviderResource`.

- [ ] **Step 4: Run the contract suites**

```bash
cd apps/runtime && python -m pytest tests/test_contract.py -q && make test-contracts
```

Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add packages/api-contract/public.openapi.json packages/sdk-typescript/src \
  apps/runtime/tests/test_contract.py
git commit -m "feat(provider): publish the profile API contract and SDK"
```

---

### Task 9: Runtime plane model and run routing

**Files:**
- Modify: `apps/runtime/uai_runtime/provider_control.py`
- Modify: `apps/runtime/uai_runtime/app.py:45-135,236-260`
- Test: `apps/runtime/tests/test_provider_control.py`

**Interfaces:**
- Produces: `ProviderProfileConfig` (`id,name,provider,base_url,api_key,api_key_ref,max_output_tokens,models`),
  `ProviderPlaneConfig` (`revision,profiles`), `ProviderProfileState`, `ProviderState` (`revision,profiles`).
- Produces: `ActiveProvider{providers, definitions, config, configured}` and
  `make_active(config: ProviderPlaneConfig, egress, *, transport=None) -> ActiveProvider`.
- Produces: `resolve_model_key(definitions: Mapping[str, ModelDefinition], model: str) -> str | None`.
- Produces: `create_app(..., provider_plane: ProviderPlaneConfig | None = None, ...)`
  replacing the `provider_config` parameter.

- [ ] **Step 1: Write the failing tests**

In `test_provider_control.py`, add three helpers next to the existing `config()`:
`profile(profile_id, model, **overrides)` returning the profile dict,
`plane(*profiles, revision=1)` returning `{'revision': revision, 'profiles': list(profiles)}`,
and `definition(key)` returning `ModelDefinition(id=key, provider='openai-compatible',
capabilities={'chat','streaming'})`. Use the existing `send(app, path, body)` helper and
copy the `body()` helper from `tests/test_capabilities.py`, extended with a `model`
argument.

```python
SSE = (b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
       b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
       b'data: [DONE]\n\n')


def test_run_routes_to_the_profile_owning_the_model():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=SSE)

    app = create_app('internal-secret', Provider(), provider_plane=plane(
        profile('first', 'alpha', base_url='http://first/v1'),
        profile('second', 'beta', base_url='http://second/v1'), revision=2))
    app.state.providers.replace(make_active(
        app.state.providers.snapshot().config, None, transport=httpx.MockTransport(handler)))
    result = send(app, '/internal/v1/runs', body(model='second/beta'))
    assert result.status_code == 200
    assert hosts == ['second']


def test_resolve_model_key_prefers_exact_then_default():
    definitions = {'default/alpha': definition('default/alpha'),
                   'other/alpha': definition('other/alpha'),
                   'default/meta-llama/Llama-3': definition('default/meta-llama/Llama-3')}
    assert resolve_model_key(definitions, 'other/alpha') == 'other/alpha'
    assert resolve_model_key(definitions, 'alpha') == 'default/alpha'
    assert resolve_model_key(definitions, 'meta-llama/Llama-3') == 'default/meta-llama/Llama-3'
    assert resolve_model_key(definitions, 'missing') is None
```

Also assert: `ProviderPlaneConfig` rejects duplicate ids, both `api_key` and
`api_key_ref`, credentials on `ollama`, ids outside `^[a-z0-9][a-z0-9-]{0,31}$`,
more than 20 profiles, and more than 1000 total models; `state_of` returns
namespaced model ids and no secret; `/internal/v1/models` returns namespaced ids.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/runtime && python -m pytest tests/test_provider_control.py -q
```

Expected: `ImportError`/`TypeError` on the plane model.

- [ ] **Step 3: Implement the plane**

`make_active` builds one adapter per profile (`OpenAIProvider` with the inline
`api_key` or the env-resolved `api_key_ref`; `OllamaProvider` without a key),
definitions keyed `f'{profile.id}/{model.id}'` with `ModelDefinition.id` set to
that key and `provider` set to the kind, and `configured[profile.id]`.
`resolve_model_key` tries the exact key, then `'default/' + model`, and returns
`None` otherwise. In `app.py`, the run handler resolves the key before the
capability and snapshot checks and picks
`active.providers[resolved.split('/', 1)[0]]`; `/internal/v1/models` iterates the
sorted definitions. `create_app` accepts `provider_plane`, and when it is absent
synthesizes a single `default` profile from the `provider`/`allowed_model`/
`model_definition` arguments exactly as today.

- [ ] **Step 4: Run the suite to verify it passes**

```bash
cd apps/runtime && python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/runtime/uai_runtime/provider_control.py apps/runtime/uai_runtime/app.py \
  apps/runtime/tests/test_provider_control.py
git commit -m "feat(provider): route runs across provider profiles"
```

---

### Task 10: Runtime compatibility, discovery and environment startup

**Files:**
- Modify: `apps/runtime/uai_runtime/provider_control.py`
- Modify: `apps/runtime/uai_runtime/app.py:395-480` (`from_env`)
- Modify: `packages/api-contract/internal.openapi.json` (regenerated)
- Test: `apps/runtime/tests/test_provider_control.py`, `apps/runtime/tests/test_contract.py`

**Interfaces:**
- Consumes: Task 9 plane models.
- Produces: `ProviderPlaneConfig` accepting a payload without `profiles` and
  wrapping it as profile `default` (name `Default`).
- Produces: `from_env` building a `default` profile with
  `api_key_ref='MODEL_API_KEY'` for `openai-compatible` and `''` for `ollama`.

- [ ] **Step 1: Write the failing tests**

- `test_plane_accepts_legacy_single_provider_payload`: validating the pre-change
  payload yields one profile `default` with the same revision and model ids.
- `test_from_env_builds_default_profile`: with `MODEL_PROVIDER=openai-compatible`
  and `MODEL_NAME=test`, `state_of` reports profile `default`,
  `api_key_ref == 'MODEL_API_KEY'`, and the model key `default/test`.
- `test_plane_limits`: 21 profiles → validation error; 1001 total models →
  validation error.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/runtime && python -m pytest tests/test_provider_control.py -q -k 'legacy or inline or from_env or limits'
```

Expected: validation errors for the legacy payload and the extra field.

- [ ] **Step 3: Implement compatibility and regenerate the internal contract**

Add a `mode='before'` validator on `ProviderPlaneConfig` that rewrites a mapping
without `profiles` into `{'revision': ..., 'profiles': [{'id': 'default', 'name': 'Default', ...}]}`.
The discovery `api_key` field and its selection already landed in Task 5. Rewire
`from_env` to build and pass the plane while still passing
`provider`/`allowed_model`/`model_definition`, so the parameterless test path is
unchanged. Regenerate the internal snapshot:

```bash
cd apps/runtime && python -c "
import json
from uai_runtime.app import create_app
from uai_runtime.provider import OpenAIProvider
print(json.dumps(create_app('internal-secret', OpenAIProvider('http://provider/v1', '')).openapi(),
                 indent=2, sort_keys=True))" > /tmp/internal.openapi.json
cp /tmp/internal.openapi.json packages/api-contract/internal.openapi.json
```

- [ ] **Step 4: Run the suite to verify it passes**

```bash
cd apps/runtime && python -m pytest tests/ -q
```

Expected: all tests pass, including `test_openapi_contracts_and_internal_snapshot`.

- [ ] **Step 5: Commit**

```bash
git add apps/runtime/uai_runtime/provider_control.py apps/runtime/uai_runtime/app.py \
  apps/runtime/tests/test_provider_control.py packages/api-contract/internal.openapi.json
git commit -m "feat(provider): accept legacy planes and inline discovery credentials"
```

---

### Task 11: Operator configuration, security checks and ADR

**Files:**
- Modify: `.env.example`, `compose.yaml`, `tests/release/check_release.py`, `tests/e2e/check_security_config.py`
- Create: `docs/adr/0014-provider-credentials-at-rest.md`
- Modify: `docs/configuration.md`, `docs/security-operations.md`, `docs/assistants-models.md`, `docs/upgrades.md`, `docs/deployment.md`, `docs/installation.md`, `docs/guide.md`, `docs/progress.md`, `docs/implementation-status.md`, `docs/adr/README.md`

**Interfaces:**
- Consumes: the `UAI_SECRET_KEY` semantics from Task 3.
- Produces: documented boot secret (`_FILE` supported) and the compose/example wiring.

- [ ] **Step 1: Write the failing check**

In `tests/e2e/check_security_config.py`, add `UAI_SECRET_KEY` to the
`.env.example` name loop and add:

```python
migration_017 = read('apps/gateway/migrations/017_provider_profiles.sql')
check('provider_profiles' in migration_017, 'migration 017 missing')
check('CREATE TABLE provider_profiles' in migration_017, 'profile table missing')
for forbidden in ('api_key text', 'secret text', 'credential text'):
    check(forbidden not in migration_017, f'plaintext credential column: {forbidden}')
check(re.search(r'^\s+UAI_SECRET_KEY:\s*\$\{', compose, re.M) is not None,
      'gateway must receive UAI_SECRET_KEY from the environment')
```

- [ ] **Step 2: Run the check to verify it fails**

```bash
python3 tests/e2e/check_security_config.py
```

Expected: `UAI_SECRET_KEY missing from .env.example` (or the compose check).

- [ ] **Step 3: Update configuration and documentation**

`.env.example`: add `UAI_SECRET_KEY=` with a comment that it is the base64 32-byte
KEK for provider credentials stored from the console, and that an empty value
disables stored credentials. `compose.yaml`: add
`UAI_SECRET_KEY: ${UAI_SECRET_KEY:-}` to the gateway service only.
`check_release.py`: add `UAI_SECRET_KEY` to the source-scan allowlist so an empty
assignment is not treated as a leak.

Write `docs/adr/0014-provider-credentials-at-rest.md` with: context (ADR 0003
required references only), decision (profiles, encrypted at rest, KEK from the
deployment, plaintext only on the internal channel), consequences (new boot
secret, no automatic rotation, environment references still supported), and
verification (Tasks 2, 3, 5, 12). Update `docs/adr/README.md` and mark ADR 0003's
provider clause superseded. Update the operator docs: secret sources and
rotation, the `/v1/providers` endpoints, the `profile/model` assistant identifier,
and the `UAI_SECRET_KEY` requirement.

- [ ] **Step 4: Run the checks**

```bash
python3 tests/e2e/check_security_config.py && make test-security && make test-release
```

Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add .env.example compose.yaml tests/e2e/check_security_config.py \
  tests/release/check_release.py docs
git commit -m "feat(provider): document and wire the credential key-encryption key"
```

---

### Task 12: End-to-end provider profile scenario and full gate

**Files:**
- Create: `tests/e2e/check_providers.py`
- Modify: `tests/e2e/run.sh`, `tests/e2e/compose.yaml`

**Interfaces:**
- Consumes: the HTTP API from Tasks 4–6, the runtime from Tasks 9–10, the KEK from Task 11.

- [ ] **Step 1: Write the failing scenario**

`check_providers.py` follows the style of `check_auth.py` (Bearer `KEY`, `BASE`,
`request()` helper) and asserts, in order:

1. `PUT /v1/providers/openai/secret` with a stored value → 200; `GET
   /v1/providers/openai` shows `secret_source:"stored"` and the body contains no
   credential value.
2. `POST /v1/providers` for a second profile using `api_key_ref` → 200.
3. `POST /v1/assistants` with `model:"openai/gpt-4o-mini"` → 201 and a streaming
   run completes against the mock provider.
4. `DELETE /v1/providers/openai` → 409 `profile_in_use`; after deleting the
   assistant → 204.
5. `psql`: `provider_profiles.secret_cipher` is non-null and does not contain the
   plaintext bytes; `provider_revision.revision >= provider_revision.applied_revision`.

Add `python3 tests/e2e/check_providers.py` to `run.sh` after
`check_agent_runs.py`, and set a fixed base64 32-byte `UAI_SECRET_KEY` in the
gateway service of `tests/e2e/compose.yaml`.

- [ ] **Step 2: Run it to verify it fails**

```bash
make e2e
```

Expected: the new script fails until the overlay env and the script are in place.

- [ ] **Step 3: Wire and implement the scenario**

Implement the script and the overlay env as described, reusing the mock provider
endpoint already present in the suite.

- [ ] **Step 4: Run it to verify it passes**

```bash
make e2e
```

Expected: `check_providers.py` passes and the other checks stay green.

- [ ] **Step 5: Commit and run the full gate**

```bash
git add tests/e2e/check_providers.py tests/e2e/run.sh tests/e2e/compose.yaml
git commit -m "test(provider): cover stored credentials end to end"
make test
```

Expected: the full gate passes (`test-capacity`, `test-contracts`, `test-release`,
`test-security`, `test-go`, `test-python`, `test-typescript`, `test-fastapi`,
`test-widget`, `test-console`, `test-go-sdk`, `test-php`).
