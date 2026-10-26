# Universal AI Kit documentation

This is the entry point for the English documentation. It includes installation,
configuration, feature references, operations runbooks, architecture decisions,
implementation plans and the acceptance report.

## Start here

| Document | Audience | What it covers |
|---|---|---|
| [Installation guide](installation.md) | Operators | Clean install, secrets, providers, profiles, verification and checklist |
| [Guide](guide.md) | Everyone | End-to-end install, configuration, API usage, RAG, tools, SDKs, operations and troubleshooting |
| [Examples](examples.md) | Developers / operators | Copy-paste API, RAG, tools, widgets, SDKs and operations examples |
| [Configuration reference](configuration.md) | Operators | Environment variables, Compose profiles, secrets and defaults |
| [Deployment](deployment.md) | Operators | Clean install, profiles, prerequisites, graceful shutdown and two installations |
| [Upgrades and rollback](upgrades.md) | Operators | Backup, forward migrations, application rollback and destructive restore |
| [Releases](releases.md) | Maintainers | Versioning, SBOM, licenses, packages, images and provenance |
| [Capacity and recovery](capacity.md) | Operators / QA | Workload, measured baseline, bounds and recovery evidence |
| [Acceptance report](acceptance-report.md) | QA / Maintainers | The 13 acceptance criteria and final gate evidence |
| [Release notes](release-notes.md) | Everyone | Current release candidate summary |

## Feature reference

### Core and API

- [Authentication and scopes](auth.md) — bootstrap key, credentials,
  roles, expiry, revocation and ownership.
- [Assistants and models](assistants-models.md) — immutable assistant
  versions, model capabilities and conditional updates.
- [Agent runs](agent-runs.md) — persistent run state, cancellation and
  replay.
- [Runtime lifecycle](runtime-lifecycle.md) — runtime/plugin lifecycle and
  verification matrix.
- Public OpenAPI: `packages/api-contract/public.openapi.json`
- Internal contract: `packages/api-contract/README.md`

### RAG and data

- [Knowledge bases](knowledge-bases.md) — ownership, versions and
  assistant associations.
- [Documents](documents.md) — upload validation, deduplication and jobs.
- [Parsing](parsing.md) — TXT/Markdown/HTML/PDF/DOCX and limits.
- [Chunking](chunking.md) — page boundaries, offsets and stable IDs.
- [Jobs](jobs.md) — durable worker claims, leases, retries and dead letters.
- [Storage](storage.md) — filesystem and optional S3-compatible blobs.
- [Embeddings](embeddings.md) — Ollama/OpenAI-compatible embeddings and
  index versions.
- [Vector store](vector-store.md) — Qdrant collections and mandatory KB
  filters.
- [Ingestion](ingestion.md) — reindex, atomic activation and export.
- [Retrieval](retrieval.md) — composable retrieval and ACLs.
- [RAG](rag.md) — `builtin.rag`, citations and provenance.
- [Data policy](data-policy.md) — retention, deletion, tombstones and
  backup expiry.

### Tools, plugins and agents

- [Tools](tools.md) — registry, scopes and tool policy.
- [HTTP tools](http-tools.md) — connectors, SSRF/DNS pinning and secrets.
- [Approvals](approvals.md) — human approval binding and expiry.
- [Tool executions](tool-executions.md) — idempotent effects, retries and
  unknown outcomes.
- [Agent loop](agent-loop.md) — multi-step tool calling.
- [Budgets](budgets.md) — step/token/context/output limits.
- [Audit](audit.md) — transactional audit and redaction.
- [Plugins](plugins.md) — trusted and isolated HTTP plugins.
- [Plugin SDK](plugin-sdk.md) — manifests, skills and local packages.
- [Agents](agents.md) — read-only/mutating gate.

### Integrations and operations

- [Integrations](integrations.md) — SDK contract matrix and coverage.
- [Console](console.md) — SvelteKit admin console.
- [Widgets](widgets.md) — widget tokens, CORS and rate limits.
- [Laravel](laravel.md) — server-side integration and Blade chat widget.
- [FastAPI](fastapi.md) — authenticated chat widget sessions and runnable example.
- [Observability](observability.md) — OpenTelemetry, metrics and logs.
- [Security operations](security-operations.md) — TLS, secrets, egress,
  rate limits and deployment hardening.
- [Backup and restore](backup-restore.md) — backup format, restore,
  RPO/RTO and Qdrant rebuild.

## Architecture and decisions

- [ADR index](adr/README.md) — architecture decision records.
- [Project specification](project-spec.md) — original product spec.
- [Implementation progress](progress.md) — chronological implementation log.
- [Task backlog](TASKS.md) — milestone/task status and acceptance mapping.
- [Implementation status](implementation-status.md) — detailed verification
  history.

## Reading paths

### Evaluate the project

1. [README](index.md)
2. [Installation guide](installation.md)
3. [Examples](examples.md)
4. [Acceptance report](acceptance-report.md) and
   [release notes](release-notes.md)

### Deploy and operate

1. [Guide: deployment](guide.md#3-deployment-profiles)
2. [Installation guide](installation.md)
3. [Configuration reference](configuration.md)
4. [Deployment](deployment.md)
5. [Security operations](security-operations.md)
6. [Backup/restore](backup-restore.md) and
   [upgrades](upgrades.md)

### Build an integration

1. [Guide: API workflow](guide.md#4-api-workflow)
2. [Examples](examples.md)
3. [Public API overview](api.md)
4. SDKs:
   `packages/sdk-typescript` ·
   `packages/sdk-go` ·
   `packages/sdk-php`
4. `packages/chat-widget` ·
   [Laravel](laravel.md)

### Work on the codebase

1. [Guide: development and tests](guide.md#11-development-and-tests)
2. [Repository layout](index.md)
3. [ADR index](adr/README.md)
4. [Runtime lifecycle](runtime-lifecycle.md)

## Documentation policy

- New pages are written in English and added to this index and the MkDocs
  navigation in `mkdocs.yml`.
- Commands in documentation are expected to run against the current repository;
  the final gate is recorded in the acceptance report.
- Historical plans and progress logs are kept for traceability; the guide and
  reference pages are the recommended reading path.
