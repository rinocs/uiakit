# Knowledge base, versions and access
Knowledge bases are gateway resources, authorized before upload,
association and retrieval. PostgreSQL is the authoritative source; vector indices
they will be derived and reconstructable in milestones M3-07…M3-09.

## Public API

You need the `knowledge-bases:read` / `knowledge-bases:write` scopes. Credentials
existing scopes do not automatically acquire new scopes. Owner and admin can
read and edit; a KB of another principal returns 404.

| Method | Path | Effect |
| --- | --- | --- |
| GET | `/v1/knowledge-bases` | Lists accessible KB |
| POST | `/v1/knowledge-bases` | Create KB + version 1 `active` |
| GET | `/v1/knowledge-bases/{id}` | Reads metadata and `active_version` |
| PATCHES | `/v1/knowledge-bases/{id}` | Update name/description; requires `If-Match` |
| DELETE | `/v1/knowledge-bases/{id}` | Delete an unreferenced KB; requires `If-Match` |
| GET | `/v1/knowledge-bases/{id}/versions` | List immutable versions |
| POST | `/v1/knowledge-bases/{id}/versions` | Create a `reindexing` version; requires `If-Match` |

GET returns `ETag: "N"`, where `N` is the `revision` of the KB. PATCH and DELETE
require `If-Match`; without header you get 428, with obsolete revision 412.
Revision is distinct from `active_version`: a new version increments the
revision but does not change the active version.

```http
POST /v1/knowledge-bases
Authorization: Bearer <operator-key>
Content-Type: application/json

{"name":"Manuals","description":"Product documentation",
 "config":{"chunk_size":500,"chunk_overlap":50}}
```

```http
POST /v1/knowledge-bases/6f1c.../versions
Authorization: Bearer <operator-key>
Content-Type: application/json
If-Match: "1"

{"config":{"chunk_size":800,"chunk_overlap":80}}
```

The first example creates version 1 `active`. The second creates a version
`reindexing` and leave 1 on until M3-09 completes the new index e
performs the atomic switch. Only one `reindexing` version is allowed per KB; one
second request returns 409.

## Configuration

Each version contains a complete configuration:

| Field | Constraint | Default |
| --- | --- | --- |
| `chunk_size` | integer 100…8000 | 1000 |
| `chunk_overlap` | integer ≥0 and `< chunk_size` | 200 |

The configuration is immutable in the version. Changing it requires a new one
version, so a partial index cannot be swapped with the active one.
When `config` is omitted in creation the defaults are used; if it is present they must
both fields exist. JSON is limited to 64 KiB in the database.

## Association with assistants

`knowledge_base_ids` is an array of UUIDs, maximum 64, without duplicates, inside the
immutable version of the server. The creation and each PATCH validate, in the
same transaction:

1. UUID format and uniqueness;
2. existence of the KB;
3. ownership of the principal or admin role;
4. shared lock of the KB row until commit.

An unknown or unauthorized ID produces 422 and does not enter the version.
Admin can bind any KB; an operator cannot associate other people's KBs.
The runtime accepts the snapshot with `knowledge_base_ids`; the actual filtering
of the retrieval will arrive with M3-10/M3-11. An unauthorized KB therefore cannot
reach runtime filters because it cannot be persisted across a version.

## Cancellation

DELETE requires `If-Match`. If a **current** version of a server
references the KB, or if the KB contains documents, the answer is 409: yes first
update the assistant/remove the documents, then delete the KB. The versions
assistant histories do not block deletion; runs already completed
they keep their own events and do not depend on the KB. KB versions come
eliminated in cascade. Documents and their storage are described in
[documents.md](documents.md) and [storage.md](storage.md).## Scheme and invariants

Migration `005_knowledge_bases.sql`:

- `knowledge_bases`: owner, name, description, `revision`, `active_version`,
  timestamp; index `(owner_id, created_at)`.
- `knowledge_base_versions`: FK `ON DELETE CASCADE` to the KB, config JSON
  bounded, status `active`/`reindexing`/`failed`, PK `(knowledge_base_id, version)`.
- FK deferred `(id, active_version)` → version, thus creating KB and
  version 1 occurs in the same transaction.
- Unique partial indexes: only one `active` version and only one `reindexing` version per KB.
- Audit: `knowledge_base.created`, `knowledge_base.updated`,
  `knowledge_base.version_created`, `knowledge_base.deleted`, no config.

## Limits

- Document upload, chunk, embedding, index and retrieval are M3-02…M3-11.
- `failed` is reserved for worker states; M3-01 does not activate automatically
  one version.
- There is no transfer of ownership or explicit sharing between principals:
  owner or admin.
- Single gateway and runtime per database, as in the current deployment.

## Evidence

- `apps/gateway/knowledge_bases_test.go`: CRUD, ETag/If-Match, versions,
  single reindexing, cross access, associations and delete guard.
- `tests/e2e/check_knowledge_bases.py`: two real principals on PostgreSQL,
  versioning, association, run with KB in snapshot, deny cross-owner, delete
  guard and waterfall; included in `make e2e`.
- Runner checks `schema_migrations` 1–5 and active KB/version.
- `apps/runtime/tests/test_context.py`: core accepts `knowledge_base_ids`
  unique and continues to reject unimplemented features.