# Universal AI Kit 0.1.0 — release candidate

Date: 2026-10-26. This is a local, unpublished release candidate.

## What it includes

- Go gateway, Python runtime, ingestion worker and SvelteKit console.
- Chat/SSE with persistence, idempotent replay, erase and recovery.
- Versioned assistants, built-in directives, trusted/isolated plugins, HTTP tools
  with approvals and audits.
- Knowledge base, upload, parsing, chunking, embedding, Qdrant, RAG and citations
  verifiable with page/offset.
- Secret file/rotation, rate limit bounded, egress allowlist, CORS widget,
  retention/deletion, backup/restore, OpenTelemetry and security matrix.
- TypeScript, Go and PHP SDK, Web Component widgets, Laravel integration.
- Capacity/recovery baseline and deployment, upgrade and rollback runbooks.

## Gate

All required gates are green: `make test`, `make build-packages`,
`make e2e`, `make e2e-upgrade`, `make e2e-two-instances`, `make e2e-restore`,
browser 13/13, security matrix, dry-run release. The detail and residual limits
They are in [docs/acceptance-report.md](acceptance-report.md).

## Artifacts

The local bundle in `release/` contains:

- `manifest.json` and `SHA256SUMS`;
- `sbom.cdx.json` (CycloneDX 1.5) and `THIRD_PARTY_NOTICES.md`;
- SDK/plugin packages (`packages/`);
- gateway/runtime/worker/console/isolated-plugin images in tar (`images/`) with
  `images.json` (tag, image ID, hash);
- release notes and acceptance report.

Image/tag: `0.1.0`. Registry publishing, npm/Composer and deployment
public are not executed by this release.

## Upgrades and rollbacks

See [docs/upgrades.md](upgrades.md). Migrations are forward-only; a
database with schema newer than the binary is rejected. Rollback with scheme
non-reversible requires `deploy/restore.sh --reset-target`, explicitly
destructive, after a verified backup.

## Known limitations

- A gateway + a database runtime; no HA/cluster.
- Rate limiter per process, not distributed.
- Ollama/S3/Qdrant opt-in real tests skipped with no endpoint (3 skips declared).
- Model weights and external licenses not included in the software SBOM.
- The release candidate is not signed by a registry; the origin of the
  artifacts is provisioned in the GitHub pipeline.

## Local verification

```bash
make test
make build-packages
make e2e
make e2e-upgrade
make e2e-two-instances
make e2e-restore
make test-console-browser
make release-dry-run
```