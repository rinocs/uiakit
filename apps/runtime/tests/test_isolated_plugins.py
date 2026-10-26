import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from uai_core.builtin.directives.tool_policy import ToolPolicyDirective
from uai_core.configuration import AssistantConfig
from uai_core.context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from uai_core.models import Message, ModelInput
from uai_core.tools import ToolExecutionError
from uai_plugin_sdk.manifest import PluginManifest
from uai_runtime.plugin_manager import PluginManager
from uai_runtime.plugins.http_plugin import IsolatedConfig, IsolatedHTTPPlugin
from uai_runtime.tool_registry import ToolExecutor

TOOL = {
    'id': 'echo', 'name': 'Echo', 'description': 'Returns text', 'version': '1.0.0',
    'connector': 'test_connector', 'timeout': 1,
    'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['text'],
                     'properties': {'text': {'type': 'string'}}},
    'output_schema': {'type': 'object', 'additionalProperties': False, 'required': ['text'],
                      'properties': {'text': {'type': 'string'}}},
}


def manifest(**changes):
    fields = dict(id='org.isolated', name='Isolated', version='0.1.0', runtime='isolated_http',
                  compatibility={'core': '>=0.1.0,<1'}, capabilities=['tools'],
                  permissions={'network': {'connectors': ['test_connector']}})
    fields.update(changes)
    return PluginManifest(**fields)


def transport(*, tools=None, status=None, manifest_body=None):
    seen = {'requests': []}

    def handler(request):
        seen['requests'].append(request)
        if status is not None:
            return httpx.Response(status, content=b'{"error":"failed"}')
        if request.url.path == '/v1/manifest':
            body = manifest_body or manifest().model_dump(mode='json')
            return httpx.Response(200, json={'protocol': 1, 'manifest': body})
        if request.url.path == '/v1/tools':
            return httpx.Response(200, json={'protocol': 1,
                                             'tools': [TOOL] if tools is None else tools})
        if request.url.path == '/v1/health':
            return httpx.Response(200, json={'protocol': 1, 'status': 'ok'})
        if request.url.path == '/v1/activate':
            return httpx.Response(204)
        if request.url.path == '/v1/deactivate':
            return httpx.Response(204)
        if request.url.path.endswith('/execute'):
            arguments = json.loads(request.content)['arguments']
            return httpx.Response(200, json={'protocol': 1,
                                             'result': {'text': arguments['text']}})
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


def plugin(mock, *, allowed=('test_connector',)):
    return IsolatedHTTPPlugin(manifest(), 'http://isolated', 'secret-token',
                              allowed_connectors=frozenset(allowed), timeout=1,
                              transport=mock)


def assistant(tool_id='org.isolated.echo'):
    config = AssistantConfig(id=uuid4(), version=1, name='Test', model='test',
                             system_prompt='Helpful')
    return config.model_copy(update={'tools': (tool_id,)})


def context(*, connector=True, grant=True):
    tool_id = 'org.isolated.echo'
    scopes = {'tools:execute'} | ({'connector:test_connector'} if connector else set())
    return ExecutionContext(
        run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='operator', scopes=frozenset(scopes),
                                     allowed_tool_ids=frozenset({tool_id}) if grant else frozenset()),
        limits=ExecutionLimits(), assistant=assistant(),
        model_input=ModelInput(model='test', system_prompt='Helpful',
                               messages=(Message(role='user', content='Hi'),)))


def test_isolated_catalog_execution_and_connector_authorization():
    mock, seen = transport()
    instance = plugin(mock)
    manager = PluginManager([(instance, IsolatedConfig)])

    assert asyncio.run(manager.activate('org.isolated', {}))
    catalog = manager.snapshot().tools.catalog()
    assert [item.id for item in catalog] == ['org.isolated.echo']
    assert catalog[0].executor == 'isolated' and catalog[0].permissions == {
        'tools:execute', 'connector:test_connector'}

    executor = ToolExecutor(manager.snapshot().tools,
                            policy=ToolPolicyDirective(allowed_connectors={'test_connector'}))
    assert asyncio.run(executor.execute(context(), 'org.isolated.echo', {'text': 'abc'})) == {
        'text': 'abc'}
    request = next(item for item in seen['requests'] if item.url.path.endswith('/execute'))
    assert request.headers['Authorization'] == 'Bearer secret-token'
    assert request.headers['X-UAI-Plugin-Protocol'] == '1'

    with pytest.raises(ToolExecutionError) as error:
        asyncio.run(executor.execute(context(grant=False), 'org.isolated.echo', {'text': 'abc'}))
    assert error.value.code == 'forbidden'
    denied_policy = ToolExecutor(manager.snapshot().tools,
                                 policy=ToolPolicyDirective(allowed_connectors=set()))
    with pytest.raises(ToolExecutionError) as error:
        asyncio.run(denied_policy.execute(context(), 'org.isolated.echo', {'text': 'abc'}))
    assert error.value.code == 'forbidden'

    assert asyncio.run(manager.deactivate('org.isolated'))
    assert manager.snapshot().tools.catalog() == []


def test_manifest_mismatch_and_remote_failure_fail_closed_without_core_breakage():
    remote = manifest(id='org.other').model_dump(mode='json')
    mock, _ = transport(manifest_body=remote)
    manager = PluginManager([(plugin(mock), IsolatedConfig)])
    assert not asyncio.run(manager.activate('org.isolated', {}))
    assert manager.status()['org.isolated'] == 'failed'
    assert manager.snapshot().tools.catalog() == []

    mock, _ = transport(status=503)
    manager = PluginManager([(plugin(mock), IsolatedConfig)])
    assert not asyncio.run(manager.activate('org.isolated', {}))
    assert manager.status()['org.isolated'] == 'failed'


def test_health_is_unavailable_when_remote_crashes_and_connector_is_rejected_early():
    mock, _ = transport(status=503)
    instance = plugin(mock)
    manager = PluginManager([(instance, IsolatedConfig)])
    # Activation fails, so health is unavailable rather than propagating the error.
    assert not asyncio.run(manager.activate('org.isolated', {}))
    assert asyncio.run(manager.health('org.isolated')).status == 'unavailable'

    with pytest.raises(ValueError, match='isolated_connector_not_allowed'):
        plugin(transport()[0], allowed=('other.connector',))


def test_invalid_remote_schema_is_rejected():
    bad = dict(TOOL, input_schema={'type': 'object', 'properties': {'text': {'type': 'unknown'}}})
    mock, _ = transport(tools=[bad])
    manager = PluginManager([(plugin(mock), IsolatedConfig)])
    assert not asyncio.run(manager.activate('org.isolated', {}))
    assert manager.snapshot().tools.catalog() == []


def test_isolation_does_not_import_remote_code():
    mock, _ = transport()
    instance = plugin(mock)
    manager = PluginManager([(instance, IsolatedConfig)])
    assert asyncio.run(manager.activate('org.isolated', {}))
    assert 'server' not in manager.snapshot().tools.catalog()[0].id


def test_remote_timeout_and_execution_crash_fail_closed():
    def timeout_handler(request):
        raise httpx.ReadTimeout('slow isolated plugin')

    manager = PluginManager([(IsolatedHTTPPlugin(
        manifest(), 'http://isolated', 'secret-token',
        allowed_connectors=frozenset({'test_connector'}), timeout=0.01,
        transport=httpx.MockTransport(timeout_handler)), IsolatedConfig)])
    assert not asyncio.run(manager.activate('org.isolated', {}))
    assert manager.snapshot().tools.catalog() == []

    def crash_handler(request):
        if request.url.path == '/v1/manifest':
            return httpx.Response(200, json={'protocol': 1,
                                             'manifest': manifest().model_dump(mode='json')})
        if request.url.path == '/v1/tools':
            return httpx.Response(200, json={'protocol': 1, 'tools': [TOOL]})
        if request.url.path == '/v1/activate':
            return httpx.Response(204)
        if request.url.path.endswith('/execute'):
            return httpx.Response(500, json={'error': 'crashed'})
        return httpx.Response(204)

    instance = IsolatedHTTPPlugin(
        manifest(), 'http://isolated', 'secret-token',
        allowed_connectors=frozenset({'test_connector'}), transport=httpx.MockTransport(crash_handler))
    manager = PluginManager([(instance, IsolatedConfig)])
    assert asyncio.run(manager.activate('org.isolated', {}))
    executor = ToolExecutor(manager.snapshot().tools,
                            policy=ToolPolicyDirective(allowed_connectors={'test_connector'}))
    with pytest.raises(ToolExecutionError) as error:
        asyncio.run(executor.execute(context(), 'org.isolated.echo', {'text': 'x'}))
    assert error.value.code == 'plugin_protocol_error'


def test_isolated_plugin_egress_denied():
    from uai_runtime.egress import EgressPolicy, parse_allowlist
    with pytest.raises(ValueError, match='egress_denied'):
        IsolatedHTTPPlugin(manifest(), 'http://isolated', 'secret-token',
                           allowed_connectors=frozenset({'test_connector'}),
                           egress=EgressPolicy(parse_allowlist('allowed:80')))
