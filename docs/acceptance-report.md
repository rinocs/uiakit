# Acceptance report — Universal AI Kit 0.1.0

Date: 2026-10-26. Local release candidate, not published. Environment: Docker
Engine 29.8.2, Docker Compose v5.6.0, Python 3.13.16, Go 1.27.1, Node 24, PHP
8.3, PostgreSQL 17.6, Qdrant 1.15.0. E2E provider/embedding: local fixtures
OpenAI-compatible/Ollama-compatible; no cloud calls.

## Result

All 13 criteria in section 20 of `PROJECT_SPEC.md` are covered. The gates
required Docker/PostgreSQL/E2E are green. The three skipped runtime tests are
optional (S3/Ollama) and **not** real dependencies are counted as successes; the
their path is covered by fixture and adapter, but has not been executed against a
external service in this environment.

## The 13 criteria

| # | Criterion | Evidence | Outcome |
|---:|---|---|---|
| 1 | Starting Docker Compose | `make e2e`, `make e2e-two-instances`; gateway awaits PostgreSQL/sani runtime | PASS |
| 2 | Ollama or OpenAI-compatible model | `tests/e2e/mock_provider.py` via OpenAI-compatible adapter; test adaptors; Ollama real opt-in skipped | PASS (fixtures); declared limit |
| 3 | Assistant via API | `tests/e2e/check.py`, `check_versions.py`; versions/auth/If-Match | PASS |
| 4 | Streaming Message | `check.py`, `check_observability.py`; SSE, persisted terminal, replay | PASS |
| 5 | Example plugins | `check_plugins.py`/`check_plugin_admin.py`; package trusted in build, API activation | PASS |
| 6 | Assistant Directive | `check_directives.py`, `check_builtins.py`; configuration by version | PASS |
| 7 | HTTP Tools | `check_agents.py`, `run_tools.py`, `check_approvals.py`; connector HTTP, auth, approval, effect | PASS |
| 8 | Upload knowledge base | `check_documents.py`, `check_worker.py`; upload→job→chunk→index | PASS |
| 9 | RAG on documents | `check_rag.py`; retrieval filtered by KB/version | PASS |
| 10 | Verifiable Quotes | `check_rag.py` compare citations with export: document, version, page, offset | PASS |
| 11 | Laravel integration | `make test-php` — 13 tests, 214 assertions; Laravel provider/service | PASS |
| 12 | Two independent instances | `make e2e-two-instances`; project, ports, credentials, networks and separate volumes | PASS |
| 13 | Updating without breaking APIs | `make e2e-upgrade` scheme 14→15, data/replay preserved; `contract_diff.py` + unit test; release workflow compare previous tag | PASS (isolated upgrade); historical baseline contract only in CI/Git |

## Gates executed

| Command | Outcome | Evidence |
|---|---|---|
| `make test` | exit 0 | runtime 341 passed + 3 skipped, worker 8, gateway Go race/vet, SDK/contract 45 ops, security 15 boundaries/73 refs, capacity, release source |
| `make build-packages` | exit 0 | TS/Go/PHP SDK, widgets, console, plugins |
| `make e2e` | exit 0 | real Docker stack: auth, SSE, replay, RAG, tool, approval, deletion, observability, recovery, performance |
| `make e2e-upgrade` | exit 0 | pattern 14→15, graceful shutdown during run, pattern 16 rejected, data/replay preserved |
| `make e2e-two-instances` | exit 0 | two concurrent stacks, isolated state and credentials |
| `make e2e-restore` | exit 0 | backup source, isolated restore, query/replay/reindex, incompatible scheme rejected |
| `make test-console-browser` | 13 passed | Chromium, accessibility, roles, KB, plugin/approval, run/SSE |
| `make test-security` | exit 0 | config scan, array 15 boundaries and 73 references |
| `make release-dry-run` | exit 0 | SBOM 329 components, 5 versioned images, SDK/plugin packages, manifest/checksum, secret scan |
| `make test-release` | exit 0 | 8 test releases + source gate |

## Tests skipped (not successful)

`make test` reports **3 skipped** in runtime:

- `tests/test_embeddings.py`: real Ollama endpoint/model not configured;
- `tests/test_storage.py`: real S3-compatible endpoint not configured;
- `tests/test_vector_store.py`: Real Qdrant endpoint not configured.E2E tests use local fixtures and Qdrant Docker; they are not declared as
verification of a real external S3/Ollama provider. The safety matrix and the
Docker gates remain green.

## Release candidates

- Version: `0.1.0` (`VERSION`).
- Local bundle: `release/` with `manifest.json`, `SHA256SUMS`, `sbom.cdx.json`,
  `THIRD_PARTY_NOTICES.md`, SDK/plugin packages, tarred OCI images,
  `images.json`, release notes and this report.
- Five versioned images: gateway, runtime, worker, console,
  isolated-plugin; `0.1.0` tag, OCI label, image ID and hash in `images.json`.
- SBOM: 329 transitive components from lockfiles; licenses validated with allowlist
  SPDX. `NOASSERTION` fails gate.
- No `npm publish`, `composer publish` or `docker push` was executed.
- Publishing, registry push, public deployment and credential rotation are
  separate actions that require explicit permission (M6-09 does not perform them).

## Residual limits

- Supported deployment: one gateway + one database runtime; nothing HA,
  distributed leases or Redis rate limiters.
- The upgrade test uses manually applied migrations 1–14, not an image
  historical; demonstrates the migration path and rejection of the future pattern.
- This workspace is missing a previous Git history/tag: the contract diff is
  verified by unit tests and release workflow; the historical baseline
  will be compared to the real tag in CI.
- S3/Ollama real and model weights were not used; their respective licenses e
  performance must be verified in the chosen deployment.
- Base images are pinned by tag; the digests/hashes of the produced artifacts
  are registered, but a registry/cosign signature has not been performed.