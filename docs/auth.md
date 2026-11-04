# Authentication, scopes and ownership

The gateway is the public border of authority. Each key is validated every time
request: SHA-256 digest of 256-bit random secret, expiry and revocation in PostgreSQL.
The bootstrap key configured with `UAI_API_KEY_SHA256` maintains M1 compatibility:
principal `bootstrap-operator`, role admin. Do not expose administrative keys to the browser.
The `_FILE` variants of the sensitive variables and the rotation procedure are in
[security-operations.md](security-operations.md).

## Initial matrix

| Roles | reader | operator | admin |
|---|---|---|---|
| models:read | yes | yes | yes |
| assistants:read | yes | yes | yes |
| assistants:write | no | yes | yes |
| conversations:read | yes | yes | yes |
| conversations:write | no | yes | yes |
| messages:read | yes | yes | yes |
| messages:write | no | yes | yes |
| knowledge-bases:read | yes | yes | yes |
| knowledge-bases:write | no | yes | yes |
| documents:read | yes | yes | yes |
| documents:write | no | yes | yes |
| agent-runs:read | yes | yes | yes |
| agent-runs:write | no | yes | yes |
| approvals:read | no | yes | yes |
| approvals:write | no | yes | yes |
| credentials:read | no | no | yes |
| credentials:write | no | no | yes |
| providers:read | no | no | yes |
| providers:write | no | no | yes |
| audit:read | no | no | yes |

The credential requires an explicit subset of the role's permissions: the role
it does not replace scopes. `conversations:read` is reserved for reading metadata
conversation about next routes; history and SSE require scopes messages.
Admin can operate on all resources, within its scopes. Operator/reader
they only access the resources of their principal. Other people's resource returns 404.
models:read is explicit: an existing key without this scope cannot read
the catalogue. Scopes for tools/plugins will be added by tasks that introduce those APIs;
`knowledge-bases:read/write` are introduced by M3-01; `documents:read/write` from
M3-03 and also cover document job status/cancel (M3-06);
`agent-runs:read/write` from M4-01; `approvals:read/write` from M4-04;
`audit:read` from M4-08, reserved for admin ([audit.md](audit.md)).

The limiter is installation-wide and configurable with `UAI_RATE_LIMIT` (default 120
requests/minute). A high value is useful only in controlled load tests; i
per-principal/distributed limits remain M6-04.

The same identity can have multiple credentials with different roles/scopes: create
a key reader with the operator's `principal_id` reads its data without
modification permissions. Only an admin with credentials:write can grant it.
Ownership remains stable on rotation and revocation: the principal is distinct from the key.

Knowledge bases belong to the principal who creates them. Reading and writing are
allowed to the owner or an admin; someone else's KB returns 404 as one
non-existent resource. The `knowledge_base_ids` association of a server comes
revalidated in creation/version transaction: IDs unknown or not
accessible produce 422 and do not enter the version snapshot. You see
[knowledge-bases.md](knowledge-bases.md).

## Administrative API

All requests require Bearer and JSON mutations:

- `POST /v1/credentials`: `{ "role": "operator", "scopes": ["assistants:read", "assistants:write", "conversations:write", "messages:read", "messages:write"] }`.
  optional `principal_id` must refer to existing identity; if omitted creates one.
  `expires_at` optional: default 30 days, future within 365 days.
- `GET /v1/credentials`: metadata of all keys; no secrets or digests.
- `POST /v1/credentials/{id}/rotate`: `{}` or `{ "expires_at": "..." }`.
  Keep principal/role/scopes and immediately invalidate the previous key for
  subsequent requests. Key revoked not rotatable: create a new credential.
- `POST /v1/credentials/{id}/revoke`: idempotent revocation; revocation of the
  same credential used to authorize the request.Creation/rotation returns `credential` and `api_key` only once. Save
the secret in your secret manager; a missed response is not recoverable
list. Create a new key or rotate target using a separate admin credential.
It is not allowed to rotate the key used to authorize the same request: use
a separate admin or bootstrap to maintain valid login even if you lose it
the answer. Rotation is not an idempotent replay: repeating it generates a new secret. Avoid
automatic retries on key management APIs; idempotence of messages remains unchanged.

Creation/rotation/revocation and audit are in the same transaction. Audit preserves
actor, action, target and timestamp, without token, digest, prompt or header. The mutations
are serialized and recheck the current authority after the lock, to prevent that
a key revoked by another admin authorizes a second mutation in the queue.

## Bootstrap and migration

Migration 002 adds principals, api_credentials, audit_events and ownership,
assigning M1 data to bootstrap-operator. No conversational data is deleted.
The runner applies orderly migrations in transaction and rejects future/inconsistent scheme.

To disable the bootstrap key: first create a scoped admin key
credentials:write, keep it and verify it; then empty UAI_API_KEY_SHA256 e
restart gateway. Without bootstrap the process starts only if at least one key exists
active admin capable of managing credentials. For operator recovery, configure
a new bootstrap hash and reboot. Keep a separate recovery admin login:
expiry or loss of rotation response may require this procedure.

## Runtime boundaries and limits

The public body of the message does not accept authority. The gateway adds principal
and scopes to the internal DTO only after authentication; the runtime requires the bearer
internal and converts claims to immutable ExecutionAuthority. The old requests
M1 internals without authority maintain bootstrap without scopes or tool grants. The provider
it only sees ModelInput. The internal bearer is a trusted service secret: it doesn't work
deployed to isolated clients or plugins.

An already authorized run uses the initial snapshot: revocation blocks new requests,
does not yet equate to retroactive cancellation of the run (M4-01). Only one gateway
supported; rate limit remains global 120 authenticated requests/minute per process,
it is not yet a limiter for principal/distributed. Scope and ownership are verified
locally in tests; Real migration and isolation requires `make e2e` on Docker.

## Scope tool — M2-07

GET /v1/tools requires tools:read, allowed for reader/operator/admin. tools:execute
it can only be assigned to operator/admin and does not enable execution by itself: it is needed
also a grant of the exact ID in the trusted context, the tool permissions and the
read-only profile supported. No new execution or installation HTTP routes.
Persisted keys retain their original scopes; the bootstrap key uses scopes
current admins. The gateway continues to pass empty allowed_tool_ids in runs
model. Details and limits in the [tool contract](tools.md).

## Scope plugin — M2-09

`plugins:read` and `plugins:write` are assignable to admin only. The first
allows catalog/health and retry of the desired item already authorized; the second
setup/removal with If-Match. They do not allow code installation,
access to tools or network grants. Key persist preserve the original scopes:
create a new key with explicit scope when necessary. The bootstrap uses the
current admin scope. The administrative changes lock checks the key again
also for writing plugins, avoiding mutations with a revoked permission
while the request was queued. Details in [plugins.md](plugins.md).