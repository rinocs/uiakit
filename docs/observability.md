# Observability

Observability is **optional and fail-open**: without a collector the gateway, the
runtime and the worker continue to serve requests. They are never exported
prompts, messages, `Authorization` headers, tokens, or secrets.

## Configuration

```dotenv
# Base OTLP/HTTP URL. Blank = no-op telemetry.
UAI_OTEL_ENDPOINT=http://otel-collector:4318
```

The optional collector is in `deploy/observability/`:

```bash
docker compose -f compose.yaml \
  -f deploy/observability/compose.observability.yaml \
  --profile observability up -d
```

The collector listens on `127.0.0.1:4318` and writes data to
`/var/lib/otel/telemetry.json` (volume `observability-data`), plus the logger
`debug`. In production replace the exporters with the chosen backend.

## Trace

The gateway extracts the W3C `traceparent` context if present, creates an HTTP span
and propagates the context to the runtime via header. The runtime creates:

- `GET/POST ...` span server;
- `runtime.run` (run ID, correlation ID, model, assistant ID);
- `provider.stream` (run ID, model);
- `tool.execute` (run ID, tool ID, risk, executor);
- `retrieval.query` (run ID, KB number).

The worker creates `ingestion.document` (document ID, attempts). Attributes do not
contain prompt/message text, tool arguments, URLs, or credentials.

`X-Trace-ID` is returned to the client on HTTP responses and SSE streams. In
this way a client can correlate a response with logs/traces without receiving
sensitive data.

## Metrics

Stable names (the cost metric is only output if the deployment declares i
prices; no price is invented):

| Metric | Main Attributes |
|---|---|
| `uai.requests` | method, route template, status |
| `uai.request.duration` | route template, status, operation |
| `uai.events` | event_type, terminal |
| `uai.tokens` | model, direction (`input`/`output`) |
| `uai.cost` (optional) | model, direction; requires `UAI_MODEL_COST_INPUT_PER_MILLION` / `UAI_MODEL_COST_OUTPUT_PER_MILLION` |
| `uai.errors` | code, operation |

Routes are normalized (`/v1/conversations/{id}/messages`), IDs are not
used as labels and templates are limited to 100 characters. Errors, timeouts,
cancel, approval and retrieval remain distinguishable via `event_type`,
`code` and `operation`.

## Structured logs

The gateway uses `slog` JSON with `trace_id`, `run_id`, `correlation_id`, route and
status. Run events do not include payloads or prompts. The runtime/worker
maintain existing application logs; the trace context is available via
OpenTelemetry.

## Fail-open and testing

The endpoint is reached asynchronously via batch exporter. If the collector
is not available:

- requests are not blocked;
- batch may lose span/metrics;
- no secrets are included in export attempts.

Tests:

- `apps/gateway/telemetry_test.go`: editing attributes, route cardinality,
  W3C propagation, no-op without endpoints.
- `apps/runtime/tests/test_telemetry.py`: redaction, span in-memory, no-op.
- `tests/e2e/check_observability.py`, included in `make e2e`: send a
  `traceparent`, checks that `X-Trace-ID` passes through gateway→runtime and that a
  complete function request with collector unreachable.

## Privacy

Do not enable exporters that automatically enrich spans with HTTP bodies
or query string. Metrics do not contain user IDs or conversations. For audits
and retention of application data see [data-policy.md](data-policy.md).