# Backup and restore

The backup is **consistent** for PostgreSQL and blob filesystems, excludes secrets and
does not include Qdrant: vector indices are reconstructible. The files of
Non-configuration secrets are included for traceability, but not overwritten
never `.env` or credentials.

## Backups

```bash
python3 scripts/bootstrap.py # new installations only; preserve existing secrets
deploy/backup.sh --output backups/$(date -u +%Y%m%dT%H%M%SZ)
```

The command:

1. pauses `gateway`, `runtime` and `worker` (except `--no-quiesce`);
2. run `pg_dump -Fc` from PostgreSQL;
3. archive the `blob-data` volume in `blobs.tar.gz`;
4. archive `compose.yaml`, `.env.example`, `configs/`, and `deploy/`;
5. writes `manifest.json` with schema version, SHA-256 checksum, times and
   `rpo_upper_bound_seconds`;
6. writes `SHA256SUMS`;
7. restart the services that were active.

Never includes `.env`, passwords, API keys, tokens, or volume files
Qdrant. For S3 use bucket versioning/replication: the project default
is the blob store filesystem.

Manual verification:

```bash
cd backups/2026-... && sha256sum -c SHA256SUMS
```

## Restore on new installation

Restore is destructive only with `--reset-target`. Preflight checks
checksum, format, `secrets_included=false` and schema compatibility BEFORE
to tap the database or blob volume.

```bash
deploy/restore.sh \
  --backup backups/2026-... \
  --reset-target \
  --start
```

The command:

1. stop gateway/runtime/worker and start PostgreSQL;
2. check checksum and backup pattern (reject pattern newer than the code);
3. recreate the `uai` database and restore the dump;
4. replaces the contents of the `blob-data` volume;
5. extract non-secret configurations into `restored-config-*` (except
   `--no-configs`);
6. writes `restore-report-*.json` with `rto_seconds` and backup RPO;
7. with `--start` starts the gateway and runtime.

Secrets are not in the backup: provide `.env` separately. The API keys and
credentials persisted in the database retain their hashes; rotate them if the
backup has been exposed or if the restore occurs on a different environment.

Without `--reset-target` the restore only accepts an empty database; a DB with
tables is rejected.

## Vector reconstruction

Qdrant is not included. After restore:

1. start `qdrant` and `worker`;
2. for each knowledge base create a new version of reindex with the same one
   configuration/embedding (or a new embedding version if you want a new one
   index):

```bash
# Example: GET /v1/knowledge-bases, GET /versions, then
curl -X POST "$UAI_BASE_URL/v1/knowledge-bases/$KB/versions" \
  -H "Authorization: Bearer $UAI_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -H "If-Match: \"$REVISION\"" \
  -d '{"config":{"chunk_size":1000,"chunk_overlap":200},"embedding":{"provider":"ollama","model":"nomic-embed-text","version":"nomic-embed-text-v1.5","dimension":768}}'
```

The gateway frees the previous collection at the same index before
insert the new version, so reindexing with the same embedding is possible;
the worker deletes/recreates the collection and activates it only when finished. The sources
deleted do not return because the reindex only reads existing `documents` lines.

## RPO/RTO

- **RPO**: the manifest declares an upper limit equal to the duration of the
  backup window; pausing services reduces the writing window. For
  Tighter RPOs schedule frequent backups and/or PostgreSQL replication.
- **RTO**: `restore-report-*.json` measures the actual restore time of
  databases and blobs; the start of Qdrant/reindex is excluded and must be measured separately.

Backup expiration must comply with [data-policy.md](data-policy.md).

## E2E verification

```bash
make e2e-restore
```

`tests/e2e/check_restore.py` creates a source stack, generates data with ownership,
story, document and quote, back up, destroy stack, start one
target stack isolated, restore, check:- RPO/RTO checksum, manifest, schema and report;
- history and replay with the same idempotency key;
- Qdrant empty after restore and reindex;
- RAG queries and citations after vector reconstruction;
- a restore with an incompatible scheme is rejected without deleting the data
  already present in the destination.

The test requires Docker, the project images, and about a minute on the stack
already built. Does not use a public API for backup/restore: scripts operate
only via Docker Compose/PostgreSQL.