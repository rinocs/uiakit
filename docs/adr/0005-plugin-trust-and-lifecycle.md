# ADR 0005 — Plugin trusted and isolated

**Status:** adopted for SDK/manifest/skill M2-08 and manager/API/persistence M2-09.
Connector isolation and process isolation remain in the future. Gate Docker verified on 2026-10-23.
**Date:** 2026-10-22.
**Related tasks:** M2-08, M2-09, M4-09, P-01. Tabs and dependencies in [backlog](../TASKS.md).
**References:** [specification](../project-spec.md), [ADR 0001](0001-functional-core.md).

## Context

Plugins in the same interpreter can read memory, network, and runtime filesystems. Manifest and capability do not constitute a sandbox.

## Alternatives considered

Installing code dynamically via API is excluded from the specification. Trusted packages installed by the operator and isolated integrations with remote protocol cover the two cases without confusing them.

## Proposed decision

Trusted plugins only from approved packages installed in the build/operator environment. Manifest validated with required core version, dependencies, config, capability and connector; explicit discovery, registration, activation/deactivation and health. Namespace names and rollback of partial registrations. Skills from approved local sources, without path traversal and without assigning them permissions. Isolated HTTP plugin in separate process/container; MCP implemented after built-in/HTTP MVP via same authorization boundary. Public API allows management of already installed plugins, not arbitrary code download/execution or hot reload.

## Consequences and limits

Trusted installation requires rebuild or administrative intervention. An application error can be isolated to the manager, but a trusted interpreter crash has no process isolation. HTTP isolation involves operational costs and a versioned protocol.

## Verification required

Incompatible manifest, cyclic dependencies, partial activation, collisions, deactivation cleanup, health and remote crash. Example: trusted and isolated; no public code installation endpoint.

## Subsequent changes

Update status and tasks with evidence when the decision is implemented. A change
incompatible requires a new ADR that replaces this one, without erasing its history.

## Implementation M2-08 — 2026-10-22

Uai-plugin-sdk package installable with Plugin/PluginRegistrar contracts
typed manifest. PEP 440 compatibility and dependency graph verified without
import/install code. Declared capabilities and connectors do not generate scope
nor grant; configuration/schema remains metadata to be validated in the future manager.
Snapshots revalidated before serialization to avoid model_copy bypass.

HookSubscriber consolidated in core, with runtime re-export: SDK and plugins not
import HTTP applications. Registrar only offers contributions, not removals
guards or issuing permits. Default Health unknown, with no false healthy state.

SkillLoader reads regular UTF-8 files up to 16KiB from approved host directories,
also installed packages. Relative descriptors and O_NOFOLLOW reject traversal,
concurrent symlinks and swaps; FDs closed even on invalid input. No fallbacks
path-based on platforms without POSIX support. Tagged delimited JSON rendering
escaped, maximum 32000 characters; inert frontmatter with no implied privileges.

Discovery, namespace enforcement on contributions, atomic registration,
config validation and administrative management remain M2-09. No new routes
publish or activate assistant.skills at this stage. Contract and tests in
[plugin-sdk.md](../plugin-sdk.md), no hostile Python sandbox declared.

## Partial implementation M2-09 — trusted manager

The manager receives installed and approved instances from the host code, along with templates
Pydantic setup with banned extras. Does not interpret config_schema: when
present must coincide with the diagram produced by the approved model. The request
activation is a complete configuration, not an implicit merge of the defaults
manifest. Host model defaults remain applicable.Contributions are prepared on separate registers and published without await fra
snapshot and active membership. The registrar limits capabilities and namespaces and not
exposes register_guard. Snapshots retain the previous selection, while
deactivation removes contributions from new selections even if cleanup
fails. Trusted instances/callbacks remain shared: it is not process isolation
nor guarantee draining of runs that are using plugin resources.

Compatible dependencies are resolved before use; activation requires dependencies
active and removal prohibits active employees. Lifecycle and health have timeouts
five seconds; exceptions are reported as failed/unavailable status and log
identifiers only. Trusted synchronous Python is not interruptible by timeout.

This block does not yet connect the manager to the HTTP runtime. Discovery from build,
persistent configuration, reconciliation after restart, run drainage,
administrative routes, example hello and E2E remain open in M2-09. The future API
it must not expose import or installation paths or declare one atomic
transaction that crosses PostgreSQL and runtime.

## Partial implementation M2-09 — runtime link and hello example

`from_env` statically approves the hello package instance installed in the build;
no entry points indicated by the request are imported. The plugin starts
inactive. Private routes expose catalog, activate/deactivate, and health con
internal key. Tool catalog, executor, directive validation and runs share
the composition of the manager. The host registries remain the owner of the recordings
subsequent; each execution captures a copy of the current membership.

Lifecycle decision: reject deactivate as long as any run/tool exists
in runtime. Avoid cleanup of still used resources without introducing tracking
implicit dependencies; it costs less administrative availability below
continuous load. New runs are rejected with 503 during lifecycle mutation.
Leases released on failed preflight, end of stream and closure; the executor tool
use the same pinning. No forced deletion of runs to deactivate.

Updated OpenAPI internal contract. Public APIs, persistence/configure e
reconciliation are implemented and verified; at boot the runtime leaves hello
inactive until the gateway reconciles. This section surpasses the previous one
limit «manager not connected to runtime».

## Implementation M2-09 — stewardship and durable desired state

PostgreSQL has a single revised plugin_configuration document
monotone and settings for approved IDs. The installed list and manifests remain
owned by the build/runtime, not the database. Complete configurations are
validated by the runtime before writing. Changes are serialized and
protected by If-Match on global review; the administrative transaction lock
recheck credential, role and scope after acquisition. SQL commit precedes
any application of the new state in Python: no HTTP calls under lock
SQL and no promise of distributed atomicity.

PUT/DELETE return 200 if applied, 202 if desired saved but
the application remains pending/failed. GET, new template requests, selections of
directives and tool catalogs try again; the boot gateway also reconciles. A restart
runtime is then recovered on demand without restarting the gateway. Not added
a polling worker. Revisions prevent rollbacks from obsolete requests
in the same runtime; after restart the gateway provides the current DB status.

Reconfiguring a dependency drains and restarts the dependents in topological order.
A pending removal lets existing runs finish and rejects new runs
that they would use an old configuration; the subsequent full reconciliation
drainage. A failed activation without active contributions does not prevent runs
independent. Finished normalized config and max 32 KiB, including default, is registered
in a separate snapshot from the object passed to the plugin callback.New public routes require admin with explicit plugins:read/plugins:write.
Config values ​​are not returned by catalog or audit; the current database
it stores them as JSON, to be protected like other sensitive data. The audit records
revision/actor/ID changed. DELETE removes desired, non-installed code, and
allows recovery after removal of a package from the build. No endpoints
installation or hot reload. Direct private routes remain trusted and controlled
fixtures; the desired public prevails at reconciliation.

Cost/Choice: Global revision may create conflicts between plugin changes
independent; the protocol supports a gateway and a runtime, with no replications either
polling. On-demand retry avoids a new service. Actual and desired state
they are displayed separately; general health does not certify every plugin.
The previous public/configure/persistence API absence limits are exceeded.
The actual Docker/PostgreSQL/E2E gates, including audit and restart, were performed with
`make e2e` on 2026-10-23; SQL migration was applied on real PostgreSQL.