import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from uai_plugin_sdk import Plugin, PluginManifest, resolve_manifests


def manifest(plugin_id='com.example.demo', **changes):
    fields = dict(id=plugin_id, name='Example', version='1.0.0', runtime='python',
                  compatibility={'core':'>=0.1.0,<1.0.0'}, capabilities=['tools','skills'],
                  permissions={'network':{'connectors':['example_api']}})
    fields.update(changes)
    return PluginManifest(**fields)


def test_manifest_matches_spec_and_permissions_are_declarations_only():
    from uai_core import ExecutionAuthority
    authority = ExecutionAuthority(principal_id='operator')
    item = manifest()
    assert item.permissions.network.connectors == frozenset({'example_api'})
    assert item.capabilities == frozenset({'tools','skills'})
    assert authority.scopes == frozenset() and authority.allowed_tool_ids == frozenset()
    assert resolve_manifests([item])[0].id == item.id
    assert not hasattr(item, 'authorize')


@pytest.mark.parametrize('changes', [
    {'id':'../escape'}, {'version':'not a version'}, {'runtime':'shell'},
    {'capabilities':['arbitrary_import']}, {'compatibility':{'core':'invalid range'}},
    {'permissions':{'scopes':['*']}}, {'permissions':{'network':{'connectors':['http://evil']}}},
    {'config':{'value':float('nan')}}, {'config':{'value':'x'*40000}},
])
def test_invalid_manifests_are_rejected(changes):
    with pytest.raises((ValidationError,ValueError)):
        manifest(**changes)


def test_compatibility_dependencies_cycles_and_deterministic_order():
    a = manifest('com.example.a')
    b = manifest('com.example.b', dependencies=[{'id':a.id,'version':'>=1,<2'}])
    assert [p.id for p in resolve_manifests([b,a])] == [a.id,b.id]
    assert [p.id for p in resolve_manifests([a,b])] == [a.id,b.id]
    with pytest.raises(ValueError,match='core_incompatible'):
        resolve_manifests([a],core_version='1.0.0')
    with pytest.raises(ValueError,match='missing_dependency'):
        resolve_manifests([b])
    with pytest.raises(ValueError,match='dependency_incompatible'):
        resolve_manifests([a,manifest('com.example.b',dependencies=[{'id':a.id,'version':'>=2'}])])
    cycle = manifest('com.example.a',dependencies=[{'id':b.id,'version':'>=1'}])
    with pytest.raises(ValueError,match='dependency_cycle'):
        resolve_manifests([cycle,b])
    with pytest.raises(ValueError,match='duplicate_plugin'):
        resolve_manifests([a,a])


def test_plugin_snapshot_and_lifecycle_do_not_claim_health_or_run_code_on_resolution():
    calls = []
    class Example(Plugin):
        def register(self, registrar):
            calls.append(registrar)
    source = manifest(config={'nested':{'value':'original'}})
    plugin = Example(source)
    source.config['nested']['value'] = 'outside'
    view = plugin.manifest
    view.config['nested']['value'] = 'caller'
    assert plugin.manifest.config['nested']['value'] == 'original'
    assert asyncio.run(plugin.health()).status == 'unknown'
    resolve_manifests([plugin.manifest])
    assert calls == []


def test_model_copy_does_not_bypass_manifest_validation():
    forged = manifest().model_copy(update={'config':{'value':float('nan')}})
    with pytest.raises(ValueError):
        resolve_manifests([forged])
    class Example(Plugin):
        def register(self, registrar):
            pass
    with pytest.raises(ValueError):
        Example(forged)


def test_sdk_installed_contracts_import_without_runtime_or_http_frameworks(tmp_path):
    import subprocess
    import sys
    result = subprocess.run([sys.executable,'-c','''
import sys
from importlib.metadata import version
from importlib.resources import files
from uai_plugin_sdk import Plugin, PluginManifest, PluginRegistrar, Skill
from uai_core.hooks import HookSubscriber
assert version('uai-plugin-sdk') == '0.1.0'
assert files('uai_plugin_sdk').joinpath('py.typed').is_file()
assert not {'fastapi','httpx','uai_runtime'} & sys.modules.keys()
assert not hasattr(PluginRegistrar,'grant_scope')
assert not hasattr(PluginRegistrar,'register_guard')
'''],cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr
    from uai_core.hooks import HookSubscriber
    from uai_runtime.hooks import HookSubscriber as LegacySubscriber
    assert HookSubscriber is LegacySubscriber
