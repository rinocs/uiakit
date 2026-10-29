# SDK plugins and local skills

The installable package uai-plugin-sdk contains PluginManifest, PluginDependency,
Plugins, PluginRegistrar, PluginHealth, Skill and SkillLoader. No matter the runtime,
FastAPI or HTTP/DB adapter. HookSubscriber is now a shared core contract, with
re-export from the old runtime module to maintain compatibility.

## Manifest and compatibility

The manifest is Python/JSON metadata, modeled according to the spec's example:

- namespaced id, name and version; Python runtime.
- compatibility.core and dependency versions expressed with PEP 440 specifiers.
- capabilities: tools, directives, hooks, skills.
- permissions.network.connectors: Connector names required, not URLs or credentials.
- config and config_schema: JSON metadata, not code or permission changes.

The parser rejects unknown fields, invalid versions/specifiers, non-capabilities
supported, invalid connector IDs, duplicate dependencies, and unfinished JSON values.
The complete manifest is bounded to 32 KiB, the list to 64 plugins and the dependencies to
64 for manifest. The SDK format is JSON/Python; it doesn't add a YAML parser.
A host with an approved YAML parser can pass the dict to the same validator.

resolve_manifests checks the installed core version (or the one passed
explicitly), presence and version of dependencies, duplicates and cycles. Use
packaging.Version/SpecifierSet and graphlib.TopologicalSorter, without algorithms
versioning or custom installation solver. Sort metadata stably
with respect to the order of the input list. Does not download or import packages.

Snapshots are revalidated by Python data before JSON serialization:
model_copy cannot hide NaN by turning it to null. Plugin keeps a
copy private JSON and return manifest detached; modify config obtained
via property does not modify the internal metadata.

The requested permissions remain declarations. The manifest has no API for
issue grant, authorize connector, or modify ExecutionAuthority. The policy
Tool runtimes and host guards remain separate from the plugin configuration.

## Plugins and registrars

Plugin requires register(registrar) and offers optional async hooks activate(config),
deactivate and health. The default health is unknown, not a dummy check.
PluginRegistrar only exposes add_tool, add_directive, add_observer and add_skill.
The tool contract reuses the ToolDefinition and Pydantic templates from the tool registry; the observers
they reuse HookSubscriber core and receive LifecycleEvent metadata-only.

The concrete manager lives in the runtime (`uai_runtime.plugin_manager.PluginManager`),
not in the SDK. Discovery occurs only from instances passed by the host; the manager
apply namespace/capability, atomic logging, config validation,
enable/disable, lease and administrative surface. Imports remain prohibited
arbitrary from manifest, hot reload and code installation via API. The profile
Both agent profiles reject non-empty assistant.skills because public skill selection
is not integrated yet. Isolated tools can execute through the host executor, but
the model loop currently selects only builtin/HTTP tools. A valid manifest does not declare an active plugin.

Lifecycle, reconciliation and verification matrix: [runtime-lifecycle.md](runtime-lifecycle.md).
Public API, revisions and limits: [plugins.md](plugins.md).

## Skills from approved sources

The host creates SkillLoader with an approved filesystem directory. It can be one
dedicated root or the skills directory of an already installed/imported Python package
administratively. The SDK does not interpret a username as a module name from
import. Zip resources require separate materialization/host approval.

The requested path is relative, without empty components, . or .., backslash, drive
Windows, NUL or absolute path. Reading uses relative descriptors and O_NOFOLLOW on
each component; a rename/symlink swap does not redirect reading to another
route. The root is chosen by the host, not by the skill content or template.Only regular UTF-8 files up to 16384 bytes are allowed. They are checked
fstat and size of bytes read to handle concurrent growth. FIFO, device,
directory and symlink are rejected; the non-blocking opening avoids waiting on FIFO.
Descriptors are also closed in case of error before the stream is created.
Loader requires POSIX dir_fd, O_DIRECTORY and O_NOFOLLOW: no insecure fallbacks
on platforms that do not offer these tools. Manifest/plugin agreements remain
importable independently of that medium.

Skill is a frozen snapshot with id, relative source and content. render produces a
JSON block delimited as an untrusted reference, with < > & escaped and maximum
32000 characters. Frontmatter and text that look like instructions are given; they don't come
interpreted as permissions, commands or changes to the operator prompt. The content
it may however contain prompt injection: the authority barrier remains in place
runtime policy/guards, not in a promise to neutralize every instruction.

## Examples

- Manifest, resolver and registrar: `packages/plugin-sdk/README.md`.
- Installed directive and selection for assistant: [plugins.md](plugins.md) e
  [`plugins/examples/hello`](`plugins/examples/hello`).
- Observational hooks: [events-hooks.md](events-hooks.md).
- Built-in tool, input/output schema and policy: [tools.md](tools.md).
- Local skills and untrusted rendering: following section e
  `packages/plugin-sdk/README.md`.

## Installation and checks

The `packages/plugin-sdk` README shows installation and
use. make plugin-sdk-test/check/build are explicit targets; make test include
the SDK suites in the runtime. requirements, pyproject runtime, Dockerfile and CI are
updated to install the package with core and packaging.

Local tests cover versions, graphs, manipulated metadata, import without framework,
permissions without grant, traversal/symlink swap, UTF-8/budget, FIFO and FD cleanup.
The SDK fixture is linked to `make e2e` together with the smoke of the hello package.
Real Docker/PostgreSQL and E2E verified with `make e2e`; the pipeline
GitHub was not run on GitHub in this session.