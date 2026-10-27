# Upgrades and rollbacks

The release is a versioned bundle (`VERSION`, manifest, SBOM, checksum). A
upgrade applies migrations only **forward**; there are no down migrations
automatic. The database is the source of truth: before any upgrade you need a
backup verified.

## Preflight

1. Read [releases.md](releases.md) and use a bundle with valid SBOMs/checksums.
2. Back up with quiescing:

   ```bash
   deploy/backup.sh --output backups/$(date -u +%Y%m%dT%H%M%SZ)
   ```

3. Verify the backup:

   ```bash
   cd backups/<timestamp> && sha256sum -c SHA256SUMS
   ```

4. Check the version: the new `VERSION` must be greater than or equal to
   the one installed. The gateway rejects a database with a schema newer than
   binary (`unsupported database schema version`), then a downgrade
   application cannot run on future scheme.
5. Check the release contract diff: no changes breaking non
   planned.

## Upgrades

Recommended order:

```bash
#1. Stop traffic and wait for runs in progress
docker compose stop gateway

#2. stop runtime and worker (the worker can finish the current job or leave
# expire the lease)
docker compose stop runtime worker

# 3. update release images/tags
# (e.g. docker compose pull or build from verified bundle)

#4. start PostgreSQL, then the new gateway: apply forward migrations
docker compose up -d --wait postgres
docker compose up -d --wait gateway

# 5. start runtime and worker, then test
docker compose up -d --wait runtime worker
curl -fsS http://127.0.0.1:8080/v1/health
```

The gateway performs migrations in an advisory lock transaction; if one
migration fails, does not start the server. After startup check:

- `schema_migrations` contains the expected version;
- login/API and a smoke test conversation;
- replay of an existing idempotency key;
- ingestion/RAG if the profile includes them;
- runtime and worker log/health.

`tests/e2e/check_upgrade.py` simulates a stack with pattern 14, start the binary
current (diagram 16), verifies data and replay, performs an orderly shutdown during
a run and finally reject a pattern 17. Command:

```bash
make e2e-upgrade
```

## Rollback

### Application rollback

It is only allowed if the schema has not changed or if the previous binary supports it
current scheme. The control is in the gateway: a newer scheme than binary
is rejected on startup. Do not attempt to edit manually
`schema_migrations` to bypass the check.

### Rollback with restore

If the upgrade applied a non-reversible migration or legacy binary
does not support schema, the only supported rollback is restore:

```bash
deploy/restore.sh \
  --backup backups/<timestamp> \
  --reset-target \
  --start
```

`--reset-target` is **explicit and destructive**: recreates database and blob volume of the
target. Without `--reset-target` restore rejects a non-empty database. The secrets
are not in the backup: provide the same `.env` or rotate the credentials. Qdrant not
it is included and must be rebuilt with reindex after the restore. Complete procedure in
[backup-restore.md](backup-restore.md).

## Two instances and upgrade

Two independent installations can be updated one at a time, but not
they share databases/volumes and are not a cluster. For an upgrade without downtime
distributed leases and multiple gateways would be needed on the same database: this is not the case
deployment supported.

```bash
make e2e-two-instances
```

The suite launches two stacks with separate projects, ports, credentials and volumes and
verify that data and API keys do not cross the border.

## Failures and recovery

- **Gateway killed during a run**: `running` is marked on restart
  `failed` with event `agent.failed` code `gateway_restarted`; the same
  idempotency key returns replay, new key works.
- **Worker killed**: the job with expired lease is resumed; the chunks don't come
  duplicates.
- **New migration on old binary**: boot rejected; restore the
  correct binary or backup, do not alter the scheme.
- **Migration failed during upgrade**: the gateway does not start; correct the
  cause or restore the backup, without starting runtime/worker against a scheme
  incomplete.