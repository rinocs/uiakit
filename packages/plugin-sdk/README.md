# Universal AI Kit Plugin SDK

Typed contracts for administrator-installed Python plugins and approved local
skill sources. This package depends on uai-core, Pydantic and packaging; it does
not import FastAPI, HTTP clients, database adapters or the runtime application.

From the repository root, install into the development environment:

```bash
python -m pip install -r apps/runtime/requirements-dev.txt -e packages/core -e packages/plugin-sdk
make plugin-sdk-test
make plugin-sdk-check
make plugin-sdk-build
```

The build target writes a wheel to packages/plugin-sdk/dist. The SDK tests also
run under make test. CI installs both workspace packages; the runtime Dockerfile
installs this SDK for subsequent trusted plugin management.

```python
from uai_plugin_sdk import PluginManifest, resolve_manifests

manifest = PluginManifest(
    id='com.example.integration', name='Example', version='1.0.0',
    compatibility={'core': '>=0.1.0,<1'}, capabilities={'tools'},
    permissions={'network': {'connectors': ['approved_api']}},
)
resolved = resolve_manifests([manifest])
```

resolve_manifests validates PEP 440 compatibility and dependency versions, rejects
missing dependencies/duplicates/cycles and returns detached metadata in stable
topological order. It does not import, install, register or activate plugin code.

Plugin exposes a manifest snapshot, register(PluginRegistrar), optional async
activate/deactivate and health. Default health is unknown. The registrar contract
accepts tools, directives, observers and skills; it does not grant scopes or remove
host guards. The concrete manager and atomic registration are M2-09.

SkillLoader takes an explicitly approved filesystem root:

```python
from pathlib import Path
from uai_plugin_sdk import SkillLoader

skill = SkillLoader(Path('/approved/plugin/skills')).load(
    'sales/SKILL.md', skill_id='com.example.integration.sales',
)
reference_text = skill.render()
```

For an installed, operator-approved package, the host may use the skills directory
next to that already imported package's __file__. No package is imported from a
manifest or skill name by the SDK. Zip resources must be materialized and approved
by the host before passing a directory; this loader does not extract archives.

The loader requires POSIX dir_fd/O_NOFOLLOW, rejects symlinks at every relative
component, traversal, devices/FIFOs/directories, oversized files and invalid UTF-8.
It closes all descriptors on failure. Raw content is at most 16 KiB; rendering is
bounded to 32000 characters, JSON encoded and delimited as untrusted reference
material, with tag characters escaped. YAML frontmatter is preserved as inert
text, not parsed as permissions. No automatic prompt mutation or assistant
activation occurs. The same authority and limits must govern later skill use.

Manifest permissions are declarations, not runtime grants. config/config_schema
are bounded JSON metadata; config schema enforcement and connector approval are
host-manager responsibilities. Trusted Python plugins run in the host interpreter;
this SDK is not a process sandbox. More details: ../../docs/plugin-sdk.md.
