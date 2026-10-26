# Performance, capacity and recovery

This page documents the **limitations already present** in the supported deployment, the
reproducible workload used to measure them and the observed baseline. It's not one
SLA: is a starting point for sizing an installation and for recognizing
a regression. The numbers are from the Docker E2E stack with provider ed
embedding fixture, therefore they isolate the cost of gateway/runtime/worker/DB and not
include the latency of a real provider.

## Reproducible workload

`tests/performance/run.py` uses only public APIs and local fixtures:

- 8 text documents (~7.5 KB each) uploaded to a knowledge base;
- 12 chat/SSE requests without retrieval, with 4 concurrent requests;
- 6 chat/SSE requests with RAG directive and citations, with 4 concurrent requests;
- 2 requests with slow provider (`__e2e_slow__`, 10 s), one of which is
  canceled while in progress;
- CPU/RAM sampling of containers every ~0.5 s and final snapshot.

Command:

```bash
# inside make e2e the stack is already ready; to save a baseline:
UAI_PERF_OUTPUT=tests/performance/baseline.json \
UAI_PERF_DOCS=8 UAI_PERF_CHATS=12 UAI_PERF_RETRIEVAL=6 \
UAI_PERF_SLOW=2 UAI_PERF_CONCURRENCY=4 make e2e

python3 tests/performance/check_baseline.py tests/performance/baseline.json
```

`make test` runs `test-capacity`, which revalidates the versioned baseline. For a
explicit comparison:

```bash
UAI_PERF_COMPARE=tests/performance/baseline.json make e2e
```

The comparison fails if a p95 exceeds twice the baseline (with at least 2 s
margin) or if chat throughput drops below 50%. The baseline is
`tests/performance/baseline.json`.

## Baseline measured

Environment: `dev-ct` host, Docker Compose E2E, `0.1.0` images, mock providers,
8-dimensional mock embedding, PostgreSQL 17.6, Qdrant 1.15.0. Measurement of
2026-10-26. Times are end-to-end from the client's perspective.

| Phase | Requests | Competition | p50 | p95 | Throughput |
|---|---:|---:|---:|---:|---:|
| Ingestion (upload → job completed) | 8 documents | single worker | 1275 ms | 1353 ms | 5.5 doc/s |
| Vector index (reindex → ​​active) | 72 chunks | single worker | — | 3014 ms | — |
| Chat/SSE | 12 | 4 | 72 ms | 78 ms | 59.3 req/s |
| Retrieval/RAG + quotes | 6 | 4 | 176 ms | 183 ms | 23.9 req/s |
| Slow provider | 2 | 2 | one canceled at ~1 s; one completed at ~10 s | — | — |

Errors: 0. All chat/retrieval responses resulted
`response.completed`; the 6 RAG requests returned 48 total citations.

Resources sampled during the workload (peak) and at the end of the workload:

| Service | CPU peak | RAM peak | RAM at end of workload |
|---|---:|---:|---:|
| gateway | 3.0% | 11.6 MB | 8.8MB |
| runtime | 7.5% | 70.5 MB | 70.5 MB |
| workers | 38.4% | 64.8 MB | 64.8 MB |
| PostgreSQL | 26.1% | 77.7 MB | 77.6 MB |
| Qdrant | 6.0% | 78.9 MB | 78.4 MB |
| mock providers | 7.2% | 19.5 MB | 19.5 MB |

The CPU is the one reported by `docker stats` (percentage of a core). The peaks
they are approximated by sampling and are used to compare executions, not to
size a production host.

## Limits and backpressure already applied

| Component | Limit | Effect |
|---|---|---|
| Gateways, requests | `UAI_RATE_LIMIT` (default 120/min) and `UAI_RATE_LIMIT_PER_PRINCIPAL` (default 120/min) | Separate global and principal budgets; widget with dedicated budget. |
| Gateway, run in flight | upstream timeout 130 s, run context 125 s | The number of in-flight runs is limited by rate × maximum duration; There is no unlimited in-memory queue. |
| Gateway, SSE | 64,000 output characters, 2 MB / 4,096 events per stream, write deadline 15 s | A slow client does not block the handler beyond the deadline; the exceeding stream ends with `agent.failed`. |
| Gateways, requests | body JSON 128 KB; document upload 20 MB (+ multipart overhead) | Input and upload are limited before parsing. |
| Runtime | `uvicorn --limit-concurrency 32`; provider timeout 30 s; run 120s; 64,000 character input/output; 4 steps, 8 tool calls, 8,192 tokens | A slow provider cannot create unlimited runtime connections; the gateway receives a bounded error. |
| Workers | one job at a time; lease 300 s; inch 2 s; 3 attempts; dead-letter | The queue is PostgreSQL, not process memory; a dead worker is recovered after the lease expires. |
| DB | pgx bounded connections; `FOR UPDATE SKIP LOCKED` | Concurrent claims do not duplicate jobs or chunks. |
| Qdrant | collection by KB version, atomic wipe/rebuild | An incomplete index is not activated. |The gateway reads the upstream stream and writes the downstream one accordingly
synchronous: if the client does not read, the backpressure goes back to the runtime instead of
accumulate an unlimited buffer. The Go test
`apps/gateway/backpressure_test.go` checks that the write deadline
kill a slow client instead of leaving the handler hanging.

## Recovery verified

`tests/e2e/check_recovery.py`, run by `make e2e`, actually kills processes:

1. **SIGKILL gateway during a run**: on restart `OpenStore` marks runs
   `running` like `failed`, adds an `agent.failed` event with code
   `gateway_restarted` and retains `run_id`/`correlation_id`. The same
   `Idempotency-Key` returns the failed stream in replay; a new key
   it works on the same conversation.
2. **Worker SIGKILL / lease expired**: job resumes, `attempts`
   increases, chunks are published only once and the chunk count
   distinct coincides with the total.
3. **Cancellation**: slow run accepts `POST /v1/agent-runs/{id}/cancel`,
   issues `agent.cancelled` and frees the connection; the gateway remains healthy.
4. **Ordered restarts** of runtimes and gateways already covered by
   `tests/e2e/run.sh` (replay, plugin, observability).

Limit stated: MVP deployment supports **one gateway and one runtime per
database**. Boot recovery assumes this uniqueness; a gateway replica
additional would require distributed leases/heartbeats and is not supported.

## Sizing

- **Runtime concurrency**: The ceiling is 32 concurrent requests. If he gets up
  `--limit-concurrency`, also increase runtime memory/CPU and check
  latency with `tests/performance/run.py`.
- **Rate limit gateway**: the default 120/min is much above the measured load
  (60 req/s with p95 78 ms corresponds to ~5 runs in flight). For larger loads
  size `UAI_RATE_LIMIT` and `UAI_RATE_LIMIT_PER_PRINCIPAL` together with
  runtime limit; don't just raise the rate limit.
- **Worker**: the baseline processes 8 fixture documents in 1.44 s and 72 chunks in
  ~3 s. The real cost depends on the parser and embedding; measure it with
  representative documents before increasing the queue or number of workers.
- **Memory**: the sum of the application processes in the baseline is approx
  300 MB (gateway + runtime + worker + DB + Qdrant). Leave margin for
  connections, provider cache, and parsing spikes; the limit of 1 GiB per
  service is the test guardrail, not a manufacturing recommendation.
- **Disk**: job queue and chunks are in PostgreSQL; the blobs are up
  filesystem/S3; Qdrant is rebuildable. The capacity of the disk depends on the
  retention (see [data-policy.md](data-policy.md)).