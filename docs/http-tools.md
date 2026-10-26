# HTTP tools and connectors

The template offers only `tool_id` and arguments. Destination, method, path,
headers and limits belong to an administrative connector; no URL, header or
credential can come from the model arguments.

## Model

`ConnectorDefinition` (runtime `uai_runtime.tools.connectors`) contains:

- `id` and `base_url` with `http`/`https` scheme, explicit host, no userinfo,
  query, fragment or path;
- `methods` (`GET`/`HEAD` for public catalog; `POST` for controlled effects gate only), exact `paths` allowed and `timeout`;
- `headers` as references `SecretRef(env=...)` or `SecretRef(file=...)`, never
  clear values; exactly one source per header. A file is reread a
  each request, then replace it rotates the secret without restart;
- `max_response_bytes`, `retry_policy` (`never`) and `private_networks` CIDR
  explicitly authorized.

`HTTPToolBinding` binds a tool to a connector, method and path. The tool uses
`ToolDefinition.executor = "http"` and a permission `connector:<id>`; the register
reject remote executors without exactly one permission connector and catalog
public reject HTTP tools with risk `write`/`destructive`; the path of
M4-05/M4-10 approved effect uses `POST` binding with durable reservation,
consumption of the approval and journal, without exposing the effect to the read-only loop.
The gateway also applies the same filter to the catalog.

```python
connectors = ConnectorRegistry([ConnectorDefinition(
    id='example', base_url='https://api.example.test', methods={'GET'},
    paths=('/lookup',), headers={'Authorization': SecretRef(env='EXAMPLE_TOKEN')},
    timeout=2, max_response_bytes=65536)])
http = HTTPToolExecutor(connectors)
http.register(registry, definition, binding=HTTPToolBinding(
    connector='example', method='GET', path='/lookup'),
    input_model=LookupInput, output_model=LookupOutput)
```

A deployment policy can restrict endpoints with
`HTTPToolExecutor(connectors, egress=EgressPolicy(...))`: the connectors whose
`base_url` is not in allowlist fail with `connector_forbidden_target` first
to resolve DNS or open connections. The runtime outbound allowlist, worker
and plugin is described in [security-operations.md](security-operations.md).

The MCP contract uses `executor = "mcp"` with the same permission connector; the
relevant executor remains in the next phase.

## SSRF and networking

Before each request the resolver resolves the name and validates **all**
returned addresses. Loopback, link-local, multicast, unspecified, reserved e
known metadata (`169.254.169.254`, `fd00:ec2::254`, `fd20:ce::254`,
`100.100.100.200`) are always negated. A private address is only permitted if
falls under `private_networks`; a global address is allowed. Mixed DNS responses
with only one invalid address are rejected in full.

The connection uses a network backend pinned to the validated address: the name
original remains in the URL and the SNI/TLS certificate, but the socket cannot be
hijacked by a second DNS resolution. Redirects are not followed, yes
they use environmental proxies (`trust_env=False`) and Unix sockets are disabled.
The requested path must be exactly one of those of the connector; him
arguments become just scalar query parameters.

## Secrets and limits

`env` references are resolved at request time. An absent value,
empty, too long or with control characters produces
`connector_secret_missing`/`connector_secret_invalid` before opening the
connection. Hop-by-hop headers and `Host` are prohibited. The resolved values do not
end up in results, exceptions or logs; if the server reflects them in the body, the
response is rejected with `connector_secret_leak`.

The body is streamed and stopped beyond `max_response_bytes`; errors
Non-2xx HTTP, redirects, invalid JSON, and timeouts produce normalized codes.
`retry_policy` remains `never`: no automatic retry. The JSON result comes
validated by the tool's schema output before returning to the caller.Tests: `apps/runtime/tests/test_http_tools.py` covers SSRF, mixed DNS/pinning,
redirects, limits, secrets, paths/permissions and no retry.