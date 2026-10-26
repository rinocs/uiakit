# Operational safety

This page describes the controls that the deployment must keep active:
secret sources, rotation, rate limit, egress and TLS termination. I
application contracts remain in [auth.md](auth.md), [http-tools.md](http-tools.md)
and [widgets.md](widgets.md).

## Network boundaries

| Component | Exposure | Networks |
|---|---|---|
| gateway | published port, loopback only except TLS reverse proxy | `backend`, `frontend` |
| console | published port, loopback only | `frontend` |
| runtime | no published port | `backend`, `model-egress` |
| workers | no published port | `backend`, `model-egress` |
| postgres, qdrant | no published port | `backend` (internal) |
| ollama | no published port | `backend`, `model-egress` |
| rustfs (profile `s3`) | published port, loopback only | `backend`, `frontend` |

`backend` is an internal Docker network. Only runtimes, workers and the providers that
they need to reach the Internet are on `model-egress`. No internal services
shares the reverse proxy network. The gateway remains the only public entrance:
do not forward `/internal/*` from the proxy.

## Secrets

Each sensitive variable takes a `_FILE` variant with an absolute path:

```text
INTERNAL_API_KEY_FILE=/run/secrets/internal_api_key
MODEL_API_KEY_FILE=/run/secrets/model_api_key
```

Rules applied by gateway, runtime and worker:

- only one source per variable: value and `_FILE` together produce an error
  start-up, never a silent choice;
- the file must be absolute, readable, UTF-8, maximum 64 KiB read; only one
  trailing newline is ignored; the resulting value can be at most 8192
  characters; NUL, internal newlines, empty or too large files are rejected;
- values ​​do not appear in logs, HTTP errors, audits or startup messages;
- a configured but unreadable file is a fail-closed error, even if the
  variable is optional.

Supported secrets: `INTERNAL_API_KEY`, `UAI_API_KEY_SHA256`, `DATABASE_URL`
(contains PostgreSQL password), `MODEL_API_KEY`, `EMBEDDING_API_KEY`,
`ISOLATED_PLUGIN_TOKEN`, `UAI_S3_ACCESS_KEY`, `UAI_S3_SECRET_KEY`. The API keys
client are never saved in the clear: `api_credentials.key_digest` contains
only SHA-256 hexadecimal.

Mounted files must be readable only by the process (for example `0400`,
container UID owner). Do not include secrets in the image, in
`compose.yaml`, in `.env.example` or in the build logs.

### Rotation

- **Client API Keys**: use `POST /v1/credentials/{id}/rotate`; the answer
  contains the new key only once. Revoke the old credential in
  same operational flow.
- **Connector secrets**: `SecretRef(file=...)` is reread on each request:
  replace the mounted file rotates value without restarting the runtime.
- **Boot secrets** (`INTERNAL_API_KEY`, provider keys, credentials
  database/S3): Replace the file or variable and reboot in a coordinated manner
  gateway, runtime and worker. The single instance does not maintain a second key
  valid internal; for this reason the rotation requires a short window of
  reboot, not a hot rollover. Remove previous files from the node after
  reboot successful.
- A rotation should never print the value: errors only report
  `invalid secret configuration`.

## Rate limits

| Variable | Scope | Default |
|---|---|---|
| `UAI_RATE_LIMIT` | installation-wide, server-side credentials | 120/min |
| `UAI_RATE_LIMIT_PER_PRINCIPAL` | single principal | 120/min |
| `UAI_WIDGET_RATE_LIMIT` | single token widget | 60/min |

The windows are fixed for 60 seconds; beyond the limit the answer is `429` with
`Retry-After: 60`. Widget budgets are separate and do not consume that
installation-wide. Maps are limited to 10 000 keys: windows expired
are cleared before admitting a new key and, if the map remains full,
the new key is rejected (`429`) instead of growing without limit.The limiter is in memory and applies to a single instance. Redis or a limiter
distributed are not enabled: Do not start gateway replicas until
There are proven lease/recovery and shared limiter. Size
`UAI_RATE_LIMIT` at least as `UAI_RATE_LIMIT_PER_PRINCIPAL` for the number of
expected principals; with defaults both are worth 120 and the limit
installation-wide becomes the constraint for a single principal. For E2E testing i
limits are raised explicitly; don't use those values ​​in production.

## Egress

`UAI_EGRESS_ALLOW` is the explicit allowlist of outbound endpoints used by
chat provider, embedding provider and isolated plugin. Format: `host:port`
separated by commas, with IPv6 in square brackets.

```text
# Local Ollama only
UAI_EGRESS_ALLOW=ollama:11434
# remote provider
UAI_EGRESS_ALLOW=api.openai.com:443
```

Failure Policy:

- variable absent: control disabled for compatibility; a deployment of
  production must set it;
- empty value: every outbound endpoint is denied;
- host or port not listed: runtime/worker startup fails with
  `egress_denied` (provider) or the tool is rejected with
  `connector_forbidden_target`;
- redirect, environment proxy and URL with userinfo remain disabled; timeouts
  they are explicit.

In Compose the default is `UAI_EGRESS_ALLOW=ollama:11434`, consistent with
Local `MODEL_BASE_URL`/`EMBEDDING_BASE_URL`. Changing provider or embedding
the allowlist must also be updated. HTTP connectors also apply:
`base_url` explicit, only paths/methods declared, headers like `SecretRef`,
DNS resolution pinned, `private_networks` declared and permanent blocking of
metadata/link-local; `TOOL_ALLOWED_CONNECTORS` limits the connectors that can be invoked.

## TLS and CORS

`deploy/reverse-proxy/nginx.conf.example` is the reference TLS terminator:
TLS 1.2/1.3, HSTS, max upload 21 MiB, buffering disabled for SSE and
unique upstream `gateway:8080`. Do not publish your gateway port on the Internet
without TLS.

The proxy does not need to add CORS headers: the gateway already applies the allowlist
exact `UAI_WIDGET_ORIGINS` for the widget and does not enable CORS for clients
server-side. Any `Access-Control-Allow-Origin: *` is an error
configuration, not an optimization.

## Checks

```bash
make test-security # config scan + array 15 boundaries + referenced tests
make test # suite core, including test-security
make e2e # real services, when Docker is available
```

`make test-security` fails if an internal service publishes ports, if a network
internal becomes public, if a literal secret appears, if TLS/HSTS is missing in the
proxy or if the credential scheme loses the digest. The matrix of the 15 trusts
boundary and referenced deny/allow tests are in
`tests/security/README.md`.