import asyncio

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from uai_core.builtin.directives.tool_policy import ToolPolicyDirective
from uai_core.context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from uai_core.models import Message, ModelInput
from uai_core.tools import ToolDefinition, ToolExecutionError
from uai_runtime.egress import EgressPolicy, parse_allowlist
from uai_runtime.tool_registry import ToolExecutor, ToolRegistry
from uai_runtime.tools.connectors import ConnectorDefinition, ConnectorRegistry, SecretRef
from uai_runtime.tools.http import HTTPToolBinding, HTTPToolExecutor, PinnedNetworkBackend, PinnedTransport


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    q: str = Field(max_length=1000)


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    answer: str = Field(max_length=1000)


def definition(**updates):
    values = dict(id='test.lookup', name='Lookup', description='Reads a lookup', version='1.0.0',
                  permissions={'tools:execute', 'connector:example'}, risk_level='read_only',
                  timeout=2, retry_policy='never', executor='http',
                  input_schema=Input.model_json_schema(), output_schema=Output.model_json_schema())
    values.update(updates)
    return ToolDefinition(**values)


def connector(**updates):
    values = dict(id='example', base_url='https://api.example.test', methods={'GET'},
                  paths=('/lookup',), headers={}, timeout=2, max_response_bytes=1024, retry_policy='never')
    values.update(updates)
    return ConnectorDefinition(**values)


def binding(**updates):
    values = dict(connector='example', method='GET', path='/lookup')
    values.update(updates)
    return HTTPToolBinding(**values)


def context(*, scopes=('tools:execute', 'connector:example'), grants=('test.lookup',)):
    return ExecutionContext(
        run_id=__import__('uuid').uuid4(), correlation_id=__import__('uuid').uuid4(),
        authority=ExecutionAuthority(principal_id='operator', scopes=frozenset(scopes),
                                     allowed_tool_ids=frozenset(grants)),
        limits=ExecutionLimits(),
        model_input=ModelInput(model='test', system_prompt='Helpful',
                               messages=(Message(role='user', content='Hi'),)))


def build(handler, *, connector_updates=None, binding_updates=None, definition_updates=None,
          resolver=None, policy=None):
    connector_updates = connector_updates or {}
    binding_updates = binding_updates or {}
    definition_updates = definition_updates or {}
    seen = {'transports': 0, 'requests': 0}

    def transport_factory(host, address):
        seen['transports'] += 1

        def respond(request):
            seen['requests'] += 1
            return handler(request)
        return httpx.MockTransport(respond)

    async def default_resolver(host, port):
        return ['93.184.216.34']

    executor = HTTPToolExecutor(ConnectorRegistry([connector(**connector_updates)]),
                                resolver=resolver or default_resolver,
                                transport_factory=transport_factory)
    registry = ToolRegistry()
    executor.register(registry, definition(**definition_updates), binding=binding(**binding_updates),
                      input_model=Input, output_model=Output)
    return registry, seen


def run(registry, *, policy=None, ctx=None, allow_connector=True):
    if policy is None and allow_connector:
        policy = ToolPolicyDirective(allowed_connectors=frozenset({'example'}))
    return asyncio.run(ToolExecutor(registry, policy=policy).execute(
        ctx or context(), 'test.lookup', {'q': 'hello'}))


def json_response(payload, status=200, headers=None):
    return httpx.Response(status, json=payload, headers=headers)


def test_connector_definition_rejects_unsafe_destinations_paths_and_plaintext_headers():
    for base_url in ['http://user:pass@api.example.test', 'https://api.example.test/v1',
                     'https://api.example.test?x=1', 'https://api.example.test#frag', 'file:///etc/passwd']:
        with pytest.raises(ValidationError):
            connector(base_url=base_url)
    for path in ['/../secret', '//evil.test/path', '/lookup?x=1', '/lookup#frag', 'lookup']:
        with pytest.raises(ValidationError):
            connector(paths=(path,))
    with pytest.raises(ValidationError):
        connector(headers={'Authorization': 'Bearer plaintext'})
    with pytest.raises(ValidationError):
        SecretRef(env='lowercase')
    with pytest.raises(ValidationError):
        connector(private_networks=('not-a-cidr',))


@pytest.mark.parametrize('address', ['127.0.0.1', '::1', '169.254.169.254', 'fd00:ec2::254',
                                     '10.0.0.1', '192.168.1.1', '172.16.0.1', 'fd00::1', '0.0.0.0',
                                     '100.64.0.1', '2002:7f00:1::', '64:ff9b::7f00:1'])
def test_unsafe_targets_are_rejected_before_any_transport(address):
    registry, seen = build(lambda request: json_response({'answer': 'ok'}),
                           resolver=lambda host, port: _addresses(address))
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_forbidden_target'
    assert seen == {'transports': 0, 'requests': 0}


async def _addresses(*items):
    return list(items)


def test_explicit_private_allowlist_permits_only_that_private_range():
    registry, seen = build(lambda request: json_response({'answer': 'ok'}),
                           connector_updates={'private_networks': ('10.0.0.0/8',)},
                           resolver=lambda host, port: _addresses('10.1.2.3'))
    assert run(registry) == {'answer': 'ok'}
    assert seen == {'transports': 1, 'requests': 1}

    registry, seen = build(lambda request: json_response({'answer': 'ok'}),
                           connector_updates={'private_networks': ('10.0.0.0/8',)},
                           resolver=lambda host, port: _addresses('127.0.0.1'))
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_forbidden_target'
    assert seen == {'transports': 0, 'requests': 0}


def test_mixed_dns_answers_are_rejected_and_one_validated_address_is_pinned():
    registry, seen = build(lambda request: json_response({'answer': 'ok'}),
                           resolver=lambda host, port: _addresses('93.184.216.34', '127.0.0.1'))
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_forbidden_target'
    assert seen == {'transports': 0, 'requests': 0}

    pinned = []
    registry, seen = build(lambda request: json_response({'answer': 'ok'}),
                           resolver=lambda host, port: _addresses('93.184.216.34'))
    executor = HTTPToolExecutor(ConnectorRegistry([connector()]),
                                resolver=lambda host, port: _addresses('93.184.216.34'),
                                transport_factory=lambda host, address: (
                                    pinned.append((host, address)) or httpx.MockTransport(
                                        lambda request: json_response({'answer': 'ok'}))))
    registry = ToolRegistry()
    executor.register(registry, definition(), binding=binding(), input_model=Input, output_model=Output)
    assert run(registry) == {'answer': 'ok'}
    assert pinned == [('api.example.test', '93.184.216.34')]


def test_pinned_backend_ignores_dns_changes_and_rejects_other_hosts():
    class FakeBackend:
        def __init__(self):
            self.calls = []

        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            self.calls.append((host, port))
            return object()

        async def connect_unix_socket(self, *args, **kwargs):
            raise OSError('disabled')

        async def sleep(self, seconds):
            return None

    fake = FakeBackend()
    backend = PinnedNetworkBackend('api.example.test', '93.184.216.34', backend=fake)
    asyncio.run(backend.connect_tcp('api.example.test', 443))
    assert fake.calls == [('93.184.216.34', 443)]
    with pytest.raises(OSError):
        asyncio.run(backend.connect_tcp('evil.example.test', 443))
    assert fake.calls == [('93.184.216.34', 443)]


def test_pinned_transport_connects_to_the_validated_address_and_keeps_the_url_host():
    requests = []

    async def serve(reader, writer):
        requests.append(await reader.read(4096))
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}')
        await writer.drain()
        writer.close()

    async def exercise():
        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            transport = PinnedTransport('api.example.test', '127.0.0.1')
            async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
                response = await client.get(f'http://api.example.test:{port}/lookup')
                assert response.status_code == 200 and response.json() == {}
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())
    assert b'GET /lookup' in requests[0]
    assert b'Host: api.example.test' in requests[0]


def test_redirects_are_rejected_without_a_second_request():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={'Location': 'http://169.254.169.254/latest/meta-data'})

    registry, _ = build(handler)
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_http_error'
    assert len(requests) == 1


def test_response_size_limit_is_enforced_while_streaming():
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(10):
                yield b'{"answer":"' + b'x' * 100 + b'"}'

        async def aclose(self):
            return None

    registry, seen = build(lambda request: httpx.Response(200, stream=Chunks()),
                           connector_updates={'max_response_bytes': 32})
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_response_limit'
    assert seen['requests'] == 1


def test_secret_headers_are_resolved_at_request_time_and_never_returned(monkeypatch):
    captured = {}

    def handler(request):
        captured['authorization'] = request.headers.get('Authorization')
        return json_response({'answer': 'ok'})

    registry, seen = build(handler, connector_updates={
        'headers': {'Authorization': SecretRef(env='EXAMPLE_TOKEN')}})
    monkeypatch.setenv('EXAMPLE_TOKEN', 'top-secret-token')
    result = run(registry)
    assert result == {'answer': 'ok'}
    assert captured['authorization'] == 'top-secret-token'
    assert 'top-secret-token' not in str(result)

    monkeypatch.delenv('EXAMPLE_TOKEN')
    registry, seen = build(handler, connector_updates={
        'headers': {'Authorization': SecretRef(env='EXAMPLE_TOKEN')}})
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_secret_missing'
    assert seen == {'transports': 0, 'requests': 0}

    monkeypatch.setenv('EXAMPLE_TOKEN', 'bad\nvalue')
    registry, seen = build(handler, connector_updates={
        'headers': {'Authorization': SecretRef(env='EXAMPLE_TOKEN')}})
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_secret_invalid'
    assert seen == {'transports': 0, 'requests': 0}


def test_connector_secret_is_not_returned_when_the_server_echoes_it(monkeypatch):
    def handler(request):
        return json_response({'answer': request.headers['Authorization']})

    registry, seen = build(handler, connector_updates={
        'headers': {'Authorization': SecretRef(env='EXAMPLE_TOKEN')}})
    monkeypatch.setenv('EXAMPLE_TOKEN', 'top-secret-token')
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_secret_leak'
    assert seen['requests'] == 1


def test_model_arguments_cannot_change_the_destination():
    captured = {}

    def handler(request):
        captured['url'] = request.url
        return json_response({'answer': 'ok'})

    registry, _ = build(handler)
    executor = ToolExecutor(registry, policy=ToolPolicyDirective(allowed_connectors=frozenset({'example'})))
    result = asyncio.run(executor.execute(context(), 'test.lookup',
                                          {'q': 'http://169.254.169.254/latest/meta-data'}))
    assert result == {'answer': 'ok'}
    assert captured['url'].host == 'api.example.test'
    assert captured['url'].path == '/lookup'
    assert captured['url'].params['q'] == 'http://169.254.169.254/latest/meta-data'


def test_http_tools_require_the_policy_connector_allowlist_and_a_read_only_shape():
    registry, seen = build(lambda request: json_response({'answer': 'ok'}))
    with pytest.raises(ToolExecutionError) as error:
        run(registry, allow_connector=False)
    assert error.value.code == 'forbidden'
    assert seen == {'transports': 0, 'requests': 0}

    assert run(registry, policy=ToolPolicyDirective(allowed_connectors=frozenset({'example'}))) == {'answer': 'ok'}

    executor = HTTPToolExecutor(ConnectorRegistry([connector()]),
                                resolver=lambda host, port: _addresses('93.184.216.34'),
                                transport_factory=lambda host, address: httpx.MockTransport(
                                    lambda request: json_response({'answer': 'ok'})))
    for updates in [{'risk_level': 'write'}, {'risk_level': 'destructive'},
                    {'permissions': {'tools:execute'}}, {'executor': 'builtin'}]:
        with pytest.raises(ValueError):
            executor.register(ToolRegistry(), definition(**updates), binding=binding(),
                              input_model=Input, output_model=Output)
    with pytest.raises(ValueError):
        executor.register(ToolRegistry(), definition(), binding=binding(connector='missing'),
                          input_model=Input, output_model=Output)
    with pytest.raises(ValueError):
        executor.register(ToolRegistry(), definition(), binding=binding(method='HEAD'),
                          input_model=Input, output_model=Output)
    with pytest.raises(ValueError):
        executor.register(ToolRegistry(), definition(), binding=binding(path='/other'),
                          input_model=Input, output_model=Output)


def test_registry_rejects_connector_permissions_on_builtin_tools():
    async def handler(params):
        return Output(answer='ok')

    with pytest.raises(ValueError):
        ToolRegistry().register(definition(executor='builtin'), input_model=Input,
                                output_model=Output, handler=handler)


def test_http_errors_are_not_retried():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, text='unavailable')

    registry, _ = build(handler)
    with pytest.raises(ToolExecutionError) as error:
        run(registry)
    assert error.value.code == 'connector_http_error'
    assert len(requests) == 1


def test_http_tool_is_catalogued_and_executed_through_the_runtime_factory():
    from test_capabilities import Provider, send
    from uai_runtime.app import create_app

    def handler(request):
        return json_response({'answer': 'ok'})

    http = HTTPToolExecutor(ConnectorRegistry([connector()]),
                            resolver=lambda host, port: _addresses('93.184.216.34'),
                            transport_factory=lambda host, address: httpx.MockTransport(handler))
    registry = ToolRegistry()
    http.register(registry, definition(), binding=binding(), input_model=Input, output_model=Output)
    app = create_app('internal-secret', Provider(), tool_registry=registry,
                     tool_policy=ToolPolicyDirective(allowed_connectors=frozenset({'example'})))
    catalog = send(app, '/internal/v1/tools').json()
    assert catalog[0]['executor'] == 'http'
    assert 'connector:example' in catalog[0]['permissions']
    assert asyncio.run(app.state.tool_executor.execute(
        context(), 'test.lookup', {'q': 'hello'})) == {'answer': 'ok'}


def test_http_post_binding_sends_json_arguments_for_controlled_effects():
    captured = {}

    def handler(request):
        captured['method'] = request.method
        captured['body'] = request.content
        return json_response({'answer': 'ok'})

    registry, _ = build(handler,
                        connector_updates={'methods': {'POST'}},
                        binding_updates={'method': 'POST'})
    assert run(registry) == {'answer': 'ok'}
    assert captured['method'] == 'POST' and b'"q":"hello"' in captured['body']


def test_connector_secret_file_is_read_at_request_time(tmp_path, monkeypatch):
    path = tmp_path / 'token'
    path.write_text('first-token')
    seen = []

    def handler(request):
        seen.append(request.headers['Authorization'])
        return json_response({'answer': 'ok'})

    registry, _ = build(handler, connector_updates={
        'headers': {'Authorization': SecretRef(file=str(path))}})
    assert run(registry) == {'answer': 'ok'}
    path.write_text('second-token')
    assert run(registry) == {'answer': 'ok'}
    assert seen == ['first-token', 'second-token']


def test_connector_secret_file_failures_are_normalized(tmp_path):
    with pytest.raises(ValidationError):
        SecretRef()
    with pytest.raises(ValidationError):
        SecretRef(env='EXAMPLE_TOKEN', file=str(tmp_path / 'token'))
    missing = SecretRef(file=str(tmp_path / 'absent'))
    from uai_runtime.tools.connectors import ConnectorTargetError
    with pytest.raises(ConnectorTargetError) as error:
        missing.resolve()
    assert error.value.code == 'connector_secret_missing'


def test_http_executor_enforces_egress_allowlist():
    executor = HTTPToolExecutor(
        ConnectorRegistry([connector()]),
        resolver=lambda host, port: _addresses('93.184.216.34'),
        egress=EgressPolicy(parse_allowlist('other.example.test:443')))
    with pytest.raises(ToolExecutionError) as error:
        asyncio.run(executor.execute(connector(), binding(), {'q': 'hello'}))
    assert error.value.code == 'connector_forbidden_target'
