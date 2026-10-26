# Trusted plugins

The runtime only loads instances approved by the host code. `from_env`
explicitly import the installed package `uai_plugin_hello`; does not read paths
Python from requests, does not install packages and does not perform hot reloads. The code
trusted runs in the same process: manifest and capability are not a sandbox.

The hello package is included in the Docker build and dev/CI dependencies. He leaves
inactive; the desired configuration is restored by the gateway. The approval
of another package requires installation in the build and modification of the list
host, followed by deploy. The API does not expand that list.

## Administrative API

Admin role and explicit scope `plugins:read` / `plugins:write` are needed.
Existing credentials do not automatically acquire new scopes.

| Method | Path | Roles | Effect |
| --- | --- | --- | --- |
| GET | `/v1/plugins` | plugins:read | Reconciles and returns manifest, actual state, desired enabled, and revision |
| PUT | `/v1/plugins/{id}` | plugins:write | Save full configuration `{enabled, config}` and try application |
| DELETE | `/v1/plugins/{id}` | plugins:write | Removes the desired configuration; does not uninstall code |
| GET | `/v1/plugins/{id}/health` | plugins:read | Health bound; inactive/unknown returns unavailable |

GET returns `ETag: "N"`; PUT and DELETE require `If-Match: "N"`.
The revision is global for the plugin configuration. Concurrent writings with
the same review produces a hit and a 412; without header you get 428.
PUT requires enabled boolean and config object complete JSON, max 32 KiB; nothing
implicit merge with config manifest. Host model defaults apply.
DELETE also allows you to remove package configurations that are no longer installed.

```http
PUT /v1/plugins/org.uai.hello
Authorization: Bearer <admin-key>
Content-Type: application/json
If-Match: "1"

{"enabled":true,"config":{}}
```

The runtime validates approved Pydantic model, namespaces, capabilities, and dependencies
config before the gateway saves the desired state. `200` with applied=true
confirm application. `202` with applied=false means saved configuration,
application pending or failed: check GET for status and possible retry.
There is no atomic transaction between PostgreSQL and Python. GET, model requests,
validations of directives and tool catalog retry reconciliation; there isn't a
background polling worker.

GET does not return config values. PostgreSQL stores them as JSON in the
current state, with last modification/actor; audit contains review, actor and
Modified IDs, with no values. Sensitive configurations require security
databases and backups; prefer references to credentials in approved templates.
They are not printed in the logs or passed to the model as plugin configuration.

## Example hello and selection for assistant

`org.uai.hello` contributes `org.uai.hello.greeting`. When the plugin is active,
a server can include that name in `directives`. The directive pressed
`Hello! ` to the current user message. The other assistants keep the message
original; everyone maintains the core's mandatory guards. Config only accepts `{}`.
After deactivation, new selections of that directive are rejected.

## Lifecycle and competition

Diagrams and verification matrix: [runtime-lifecycle.md](runtime-lifecycle.md).

Each run and tool acquires a snapshot and a lease until completion/error/exit.
Removing or reconfiguring active plugins waits for all executions
finish. PUT can then reply 202. The runtime rejects new runs with 503
while an old active configuration must be removed: the following requests
they try again after drainage. Runs already started are not cancelled.Dependents are removed before dependencies and reactivated after them.
A configuration requires its dependencies to be enabled. Versions/cores
they are controlled by the SDK resolver. The revision prevents obsolete applications
in the same runtime process; Same revisions with different configurations come
refuse. After restart, the latest desired state is read back from the database.

A failed activation does not publish partial contributions. The status failed and health
unavailable make the problem visible; independent runs can continue.
A failed cleanup leaves the contributions removed, but may require a restart
resources that the trusted code did not close. The system cannot terminate Python
synchronous blocking. Lifecycle and health async have five-second timeouts.

The selection uses the current host registries and active contributions, keeping separate
snapshots already started. Tool catalog and executor use the same composition.
Declaring permission does not grant scope, tool access, or network access.

## Internal surface and operating limits

The private network exposes `/internal/v1/plugins`, `/validate`, `/reconcile`,
`/{plugin_id}/activate`, `/{plugin_id}/deactivate`, `/{plugin_id}/health` with key
internal. The two direct lifecycle operations serve host/fixture control;
in production use the persistent public surface, which remains authoritative.
Reset can overwrite a private manual activation.

One gateway and one runtime process supported, as in the current deployment. It's not a
protocol for distributed stateful runtime replication. Database loss
prevents reconciliation; a validation error after upgrade requires a
administrative configuration repair. General health is not guaranteed
that each plugin is active: use catalog and health plugin.

## Evidence

Local suites cover staging, namespaces, dependencies, config, selection revocations,
ETag, privileges, retry, simulated restart, failure isolation and concurrent leases.
`tests/e2e/check_plugins.py` checks the runtime in the container;
`check_plugin_admin.py` prepares public administration, race on revisions,
selection for assistant and separate restart of runtime and gateway. The runner includes
also SQL persistence/audit controls. These tests were performed with
Real Docker and PostgreSQL via `make e2e`; the GitHub pipeline was not
run on GitHub in this session.

## HTTP isolated plugins

A manifest with `runtime: "isolated_http"` describes an external service, not
code imported into the runtime process. The host approved manifest is in
`configs/plugins/isolated-example.json`; the remote service must declare it
same `id`, `version`, `runtime`, capability and connector. The host client lives in
`apps/runtime/uai_runtime/plugins/http_plugin.py`.

### Protocol versioned

Each request uses `Authorization: Bearer <token>` e
`X-UAI-Plugin-Protocol: 1`; each JSON response returns `"protocol': 1`.
Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/v1/health` | `{"status":"ok"}` or unavailable |
| GET | `/v1/manifest` | remote manifest compared to the approved one |
| GET | `/v1/tools` | bounded catalog of read-only tools |
| POST | `/v1/activate` | activation with validated config |
| POST | `/v1/deactivate` | resource release |
| POST | `/v1/tools/{local_id}/execute` | running `{arguments: ...}` |

The catalog is validated: JSON Draft 2020-12 schema, timeout ≤ 30 s, local ID,
connector declared in the host manifest and allowlist. Every tool becomes
`<plugin_id>.<local_id>`, with `tools:execute` permissions and
`connector:<connector>`, executor `isolated` and risk `read_only`. The normal
`ToolPolicyDirective` remains mandatory: grant, scope, assistant selection and
connector allowlist are never delegated to the plugin.### Configuration

Runtime variables:

```dotenv
TOOL_ALLOWED_CONNECTORS=isolated_example
ISOLATED_PLUGIN_URL=http://isolated-plugin:8090
ISOLATED_PLUGIN_TOKEN=<secret>
ISOLATED_PLUGIN_MANIFEST=/app/configs/plugins/isolated-example.json
```

If `ISOLATED_PLUGIN_URL` is absent the plugin is not registered. Tokens or
Missing manifests fail closed. The example service uses
`plugins/examples/isolated-http/server.py`; the image
`deploy/docker/isolated-plugin.Dockerfile` runs non-root, with filesystem
read-only, `cap_drop: ALL` and `no-new-privileges`, on the internal backend network.
`tests/e2e/compose.yaml` starts the container and `check_isolated_plugin.py` checks
authentication, catalog, health, activation and removal.

A `runtime: python` plugin remains **trusted**: it runs in the host process and does not have
sandbox. HTTP isolation reduces plugin crashes, timeouts and network access,
but it doesn't promise a sandbox against hostile code; trust remains a category
distinct and administrative. See [audit.md](audit.md) for the trail
activations and [tools.md](tools.md) for authorization.