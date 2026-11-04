# Provider credentials and multiple providers — design

**Status:** proposed, awaiting approval.
**Date:** 2026-10-27.
**Supersedes:** the "provider secrets via references only" clause of
[ADR 0003](../../adr/0003-authorization-and-secrets.md) for provider credentials
(a new ADR 0014 records the replacement; ADR 0003 keeps its history).

## 1. Decision summary

1. Replace the singleton provider configuration with **provider profiles**: each
   profile has an `id`, a kind (`openai-compatible` | `ollama`), a `base_url`, its
   own credential and its own model catalog.
2. Credentials can be entered from the console. They are stored **encrypted in
   PostgreSQL** (AES-256-GCM, key-encryption key from the gateway environment) and
   are never returned by any API.
3. Environment references (`MODEL_API_KEY`, `PROVIDER_API_KEY_*`) remain
   supported, per profile, and are mutually exclusive with a stored value.
4. An assistant binds to a model as `profile/model`, so different assistants can
   use different providers and different keys.

## 2. Why

Today a deployment has exactly one provider. An operator who wants two keys (for
example one per team, or one per agent) or two providers (for example a hosted API
plus a local Ollama) must run two installations. The requested capability is
per-agent and per-provider credentials managed from the console.

## 3. Constraints found in the current system

| Constraint | Where |
| --- | --- |
| provider config is a singleton row | `apps/gateway/migrations/016_provider_configuration.sql` |
| only secret *names* are stored; values resolve from runtime env or `_FILE` | `apps/runtime/uai_runtime/provider_control.py` (`resolve_api_key`), `apps/runtime/uai_runtime/secrets.py` |
| runtime holds one adapter plus one `id → ModelDefinition` map | `ActiveProvider`, `ProviderRegistry` in `provider_control.py` |
| assistant model is a single string, validated against the synced catalog | `apps/gateway/assistant_store.go:195`, `model_configurations` table |
| assistant versions are immutable (DB trigger) | `migrations/003_assistant_versions_models.sql` |
| runtime pushes/pulls the config over the internal bearer, both on save and by 2s poll | `provider.go` (`/desired`, `/applied`, `/apply`), `provider_control.control_loop` |
| contract changes are diffed against the previous tag; breaking changes need a major version | `docs/releases.md` |
| migrations are forward-only; rollback means restoring a verified backup | `docs/upgrades.md` |

## 4. Approaches considered

**A. Encrypted in PostgreSQL (chosen).** The console writes the value; the gateway
encrypts it with a KEK from its environment; the runtime receives the plaintext
over the existing internal channel and keeps it in memory. No new volumes, the
runtime stays `read_only`, backups carry ciphertext, the console becomes the real
source of truth. Cost: a new required boot secret, ~80 lines of crypto, a key
version column for future rotation, and plaintext on the internal wire.

**B. Files on a shared volume.** The gateway writes the key to a file that the
runtime mounts read-only (the `*_FILE` path already exists). No ciphertext in the
DB. Cost: a writable volume for the gateway plus a new mount for the runtime,
bound to a single host, secrets missing from backup/restore, orphan files to
clean up.

**C. External secret manager (Vault, SSM).** Rejected: adds infrastructure the
project does not have and an operational dependency with no current requirement.

Both A and B were viable; A was chosen for portability and because the console
must be authoritative.

**Data model.** Two shapes were possible for "different key per agent": profiles
with per-profile credentials (chosen) or credentials attached directly to each
assistant. The latter duplicates `base_url` and the model catalog on every agent
and creates a second place where credentials live; profiles subsume it — an agent
that needs its own key gets its own profile.

## 5. Data model

Migration `017_provider_profiles.sql`.

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
```

Two counters, both maintained in the writing transaction:

- `provider_profiles.revision` — optimistic concurrency for one profile (`ETag`,
  `If-Match`). Bumped on every update of that profile.
- `provider_revision.revision` — global, monotonic. Bumped on every profile write;
  each write also copies the new value into `provider_profiles.config_seq`. The
  runtime reports the global revision it applied; a profile is `applied` when
  `provider_revision.applied_revision >= provider_profiles.config_seq`. One
  counter is not enough (it would make two admins editing different profiles
  conflict) and per-profile counters alone cannot describe an atomic snapshot.

Limits, enforced in the gateway and the runtime: ≤ 20 profiles, ≤ 50 models per
profile, ≤ 1000 model definitions overall.

Migration: the existing singleton row becomes profile `default` (name `Default`),
its `models` jsonb becomes `provider_profile_models` rows, `secret_ref` is kept,
`secret_cipher` stays `NULL`. `provider_revision` is seeded from the legacy
revision. The legacy `provider_configuration` table is left in place, unread and
unwritten, for one release to keep a manual rollback possible; it is dropped in a
later migration.

## 6. Credential storage

- KEK: `UAI_SECRET_KEY` (or `UAI_SECRET_KEY_FILE`), resolved with the existing
  `secretFromEnv` loader, base64 decoding to exactly 32 bytes. Set but invalid →
  the gateway refuses to start (`invalid secret configuration`), consistent with
  other boot secrets. Absent → stored credentials are disabled; every attempt to
  save one returns 503 `secret_key_unavailable`.
- Encryption: AES-256-GCM, 12-byte random nonce from `crypto/rand`, AAD
  `provider-credential:v1:<profile_id>` (binds ciphertext to the profile row),
  ciphertext plus tag stored in `secret_cipher`, nonce in `secret_nonce`,
  `secret_key_version = 1`.
- Plaintext length allowed: 1–4096 bytes UTF-8; rejected if it contains `\n`,
  `\r` or `\0`.
- Decryption happens only when the gateway builds an internal payload: apply
  push, `/desired` poll, credential pre-save validation, and discovery with a
  stored credential. A version the gateway cannot handle yields
  `secret_unreadable` (502) instead of a silent fallback.
- Precedence: a stored value and an environment reference are mutually exclusive
  (DB `CHECK`), so there is no "which wins" rule.
- Rotation of the KEK is out of scope for this change: the operator re-enters the
  credentials. `secret_key_version` exists so a dual-key rotation can be added
  without another migration.
- Secrets never appear in: public responses (`secret_source`,
  `secret_configured`, `secret_readable` only), audit details (events name the
  profile id), gateway or runtime logs.

## 7. Public API

New endpoints, scopes unchanged (`providers:read` / `providers:write`). A separate
write-secret scope was considered and rejected: an operator who can change
`base_url` can already redirect the credential to their own endpoint, so the
distinction would not hold.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/v1/providers` | list: `{"profiles": [ProviderProfileView]}` |
| POST | `/v1/providers` | create; body carries `id`, `name`, `provider`, `base_url`, `max_output_tokens`, `models`, optional `secret` |
| GET | `/v1/providers/{id}` | `ETag: "<revision>"` |
| PUT | `/v1/providers/{id}` | `If-Match` required; `name`, `provider`, `base_url`, `max_output_tokens`, `models` |
| DELETE | `/v1/providers/{id}` | 409 `profile_in_use` when any assistant uses one of its models |
| PUT | `/v1/providers/{id}/secret` | body `{source:"stored", value}` or `{source:"env", ref}`; write-only |
| DELETE | `/v1/providers/{id}/secret` | clears both sources |
| POST | `/v1/providers/{id}/models/discovery` | gateway resolves the credential server-side |

Profile view:

```json
{
  "id": "openai", "name": "OpenAI", "provider": "openai-compatible",
  "base_url": "https://api.openai.com/v1",
  "secret_source": "stored", "secret_configured": true, "secret_readable": true,
  "max_output_tokens": 1024, "revision": 3, "applied": true,
  "models": [{"id": "gpt-4o", "capabilities": [], "context_window": null}]
}
```

`secret_source` is `none` | `stored` | `env`. When the runtime was started from
environment configuration and no profile exists, GET `/v1/providers` reports a
synthetic `default` profile with `managed: false`, mirroring today's
`providerView` behaviour.

Legacy `/v1/provider` and `/v1/provider/models` stay as aliases of the `default`
profile so the OpenAPI diff is additive and the release does not need a major
version. They cannot change the profile `id` or `kind`.

Errors added to the contract: `profile_in_use`, `not_found`, `invalid_profile_id`,
`too_many_profiles`, `secret_key_unavailable`, `secret_unreadable`,
`secret_value_invalid`.

## 8. Internal control plane

`GET /internal/v1/provider/desired` and `POST /internal/v1/provider/apply` carry
the whole plane atomically:

```json
{
  "revision": 12,
  "profiles": [{
    "id": "openai", "name": "OpenAI", "provider": "openai-compatible",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...", "api_key_ref": "",
    "max_output_tokens": 1024,
    "models": [{"id": "gpt-4o", "capabilities": [], "context_window": null}]
  }]
}
```

Exactly one of `api_key` (stored value, decrypted) and `api_key_ref` (env name,
resolved inside the runtime) is non-empty; Ollama has neither. The response of
`/apply` and `/state` omits `api_key` and reports `api_key_configured` per
profile. `POST /internal/v1/provider/applied` now carries the global revision, and
the gateway records it in `provider_revision.applied_revision`.

Discovery gains an optional `api_key` field for a stored credential, keeping
`api_key_ref` for the env path.

## 9. Runtime

- `ProviderProfileConfig` replaces the singleton `ProviderConfig`: `id`, `name`,
  `provider`, `base_url`, `api_key`, `api_key_ref`, `max_output_tokens`, `models`.
  Validation keeps every current rule and adds: unique profile ids, at most one
  credential source, `[a-z0-9][a-z0-9-]{0,31}` ids, Ollama has no credential and
  no extra capabilities.
- `ActiveProvider` becomes: `revision`, `providers: Mapping[profile_id, ModelProvider]`,
  `definitions: Mapping[str, ModelDefinition]`, `configured: Mapping[profile_id, bool]`.
  Model definition keys are namespaced: `ModelDefinition.id = "profile/model"`;
  `ModelDefinition.provider` keeps the kind.
- Run routing resolves the stored key in this order: an exact `definitions[key]`
  match first, otherwise `definitions["default/" + key]`, otherwise 422
  `model_unavailable`. The resolved key is then split at the first slash to pick
  the adapter: `providers[key.split("/", 1)[0]]`. Splitting is unambiguous
  because profile ids cannot contain `/`; the fallback exists because model ids
  may already contain slashes (`meta-llama/Llama-3`), so "no slash means default"
  would misparse legacy rows.
- The exact-then-default fallback is the backward compatibility mechanism for
  assistants saved before this change: their stored `model` stays untouched and
  immutable history is preserved. Exact match wins, so a legacy id such as
  `meta-llama/Llama-3` keeps pointing at the default profile even after an
  administrator creates a profile named `meta-llama`.
- `/internal/v1/models` returns namespaced definitions only.
- A payload without `profiles` (an older gateway during a rolling upgrade) is
  accepted and wrapped as profile `default`, so a mixed-version pair keeps
  working.
- Startup from environment configuration (no gateway config) becomes one
  `default` profile built from `MODEL_*`, with `api_key_ref = "MODEL_API_KEY"`.
- Limits: `_MAX_PROFILES = 20`, models per profile ≤ 50, definitions ≤ 1000.

## 10. Console

- `apps/console/src/routes/providers/+page.{server.ts,svelte}`: list (id, name,
  kind, base_url, credential source, applied, model count) and create.
- `apps/console/src/routes/providers/[id]/+page.{server.ts,svelte}`: edit fields,
  credential panel, model table, add/remove model, discovery.
- Credential panel: write-only password input with "Salva chiave" and "Usa
  variabile d'ambiente" / "Rimuovi chiave"; it shows `secret_configured` and, for
  the env path, the reference name. When `UAI_SECRET_KEY` is missing the panel
  states that stored credentials are unavailable.
- `/provider` becomes a 308 redirect to `/providers`; the navigation link is
  renamed.
- Assistant editor: the model `<select>` is populated with namespaced values and
  grouped by profile name; an assistant saved with a bare model is preselected as
  `default/<model>`.
- Copy follows the existing Italian UI style; forbidden/`canManage` handling is
  reused unchanged.

## 11. Compatibility and migration

1. `017` creates the new tables, copies the legacy row and models into `default`,
   seeds the revision, leaves `provider_configuration` untouched.
2. The gateway switches reads and writes to the new tables; `SyncModels` keys
   become namespaced, and the two assistant-side lookups
   (`assistant_store.go` model validation, `AssistantsUsingModel`) resolve with the
   same exact-then-`default/`-fallback rule through one shared helper.
3. Existing assistants keep working without being re-saved; saving a new version
   writes the namespaced id.
4. The old columns and table stay for one release; a later migration drops them.
5. Rollback is a backup restore, as for any migration (`docs/upgrades.md`).

## 12. Security analysis

- **Database dump**: gives ciphertext only; the KEK lives in the gateway
  environment (or a mounted file), so a dump alone does not reveal credentials.
- **Gateway compromise** reveals stored credentials — but the gateway already
  receives plaintext at apply time and talks to the runtime, so this is the same
  blast radius as today's environment model (where any container can read the
  env). Documented, accepted.
- **Plaintext on the internal wire**: same trust level as `INTERNAL_API_KEY`,
  over the `backend` network, no introspection in the current deploy; the payload
  must never be logged (explicit test).
- **Downgrade**: a missing or unreadable KEK fails loudly (503/502); it never
  falls back to an environment reference, which could silently switch the
  deployment to a different credential.
- **Authorization**: unchanged scopes; every write is audited with the profile id
  and never with the value (`provider.secret.set`, `provider.secret.clear`,
  `provider.created`, `provider.updated`, `provider.deleted`).
- **Input limits** (lengths, base64, UTF-8, no newlines) protect the ciphertext
  columns and the internal payload.

## 13. Verification

Per component:

- `cd apps/gateway && go test ./...` — new `provider_secrets_test.go` (AAD
  mismatch, nonce uniqueness, version mismatch, oversize), `provider_store_test.go`
  (exclusivity, `config_seq`/`applied`), `provider_test.go` (RBAC per endpoint,
  `If-Match`, `profile_in_use`, no secret in responses, audit details), plus the
  assertion that the internal apply body contains the decrypted value while the
  public body does not.
- `cd apps/runtime && python -m pytest` — `test_provider_control.py` (multi-profile
  apply, routing by namespaced key, bare-key alias, env-ref fallback, duplicate
  ids, both-credentials rejection, legacy payload, secret never in state),
  `test_app.py` (run routed to the right adapter).
- `cd apps/console && npm test` and `make test-console-browser` — providers pages,
  credential panel states, assistant model select, navigation and accessibility.
- `make test-contracts` — regenerated `generated.ts` and the OpenAPI diff.
- `make test-security` — extended configuration checks (KEK absent ⇒ stored
  credentials refused; no secret material in artifacts).
- `make test` — the full gate.

## 14. Documentation

New `docs/adr/0014-provider-credentials-at-rest.md` recording the replacement of
ADR 0003's reference-only rule; updates to `docs/configuration.md`,
`docs/security-operations.md`, `docs/assistants-models.md`, `docs/guide.md`,
`docs/installation.md`, `docs/deployment.md`, `docs/progress.md`,
`docs/implementation-status.md`, `.env.example` (`UAI_SECRET_KEY`) and
`compose.yaml` (gateway environment).

## 15. Out of scope

- Automatic KEK rotation and a CLI to re-encrypt.
- Per-assistant credentials that are not expressed as a profile.
- Embedding/reranker providers (they keep their own configuration).
- Storing credentials for connectors or tools.

## 16. Delivery split

Two plans, each producing working software:

1. **Backend**: migration + crypto + gateway endpoints + internal payload +
   runtime multi-profile, verified by Go and Python tests and the CLI-only
   console paths through the SDK.
2. **Console**: providers pages, redirect, assistant model select, browser tests,
   copy and documentation.

The console plan depends on the backend plan being merged.
