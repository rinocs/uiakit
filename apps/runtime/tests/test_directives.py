import asyncio
from uuid import uuid4

import pytest

from uai_core.context import ExecutionContext, ExecutionAuthority, ExecutionLimits
from uai_core.models import ModelInput, Message
from uai_core.directives import Directive, DirectiveRegistry, DirectiveError


def context():
    return ExecutionContext(run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='caller'), limits=ExecutionLimits(),
        model_input=ModelInput(model='test', system_prompt='Protected',
                              messages=(Message(role='user', content='Hi'),)))


class Record(Directive):
    def __init__(self, calls, **kwargs):
        super().__init__(**kwargs)
        self.calls = calls

    async def before_model(self, context):
        self.calls.append(self.name)
        return context.with_messages((Message(role='user', content='Changed'),))


def test_dependency_order_and_stable_ties():
    calls = []
    registry = DirectiveRegistry()
    for name, priority, deps in [('z', -10, ('a',)), ('b', 0, ()), ('a', 0, ())]:
        registry.register(Record(calls, name=name, priority=priority, depends_on=deps))
    pipeline = registry.build(('z', 'b', 'a'))
    result = asyncio.run(pipeline.apply('before_model', context()))
    assert calls == ['a', 'z', 'b']
    assert result.model_input.messages[0].content == 'Changed'


def test_invalid_configuration_and_mandatory_selection():
    registry = DirectiveRegistry()
    guard = Directive(name='guard')
    registry.register(guard, mandatory=True)
    with pytest.raises(ValueError):
        registry.register(Directive(name='guard'))
    assert registry.build(()).names == ('guard',)
    with pytest.raises(ValueError):
        registry.build(('unknown',))
    registry.register(Directive(name='missing', depends_on=('absent',)))
    with pytest.raises(ValueError):
        registry.build(('missing',))
    registry.register(Directive(name='a', depends_on=('b',)))
    registry.register(Directive(name='b', depends_on=('a',)))
    with pytest.raises(ValueError):
        registry.build(('a', 'b'))


@pytest.mark.parametrize('field,value', [
    ('authority', ExecutionAuthority(principal_id='admin', scopes={'*'})),
    ('limits', ExecutionLimits(max_input_chars=999999)),
    ('run_id', uuid4()), ('correlation_id', uuid4()),
    ('assistant', 'forged'), ('model_definition', 'forged'),
])
def test_protected_fields_fail_closed_even_with_continue(field, value):
    class Escalate(Directive):
        async def before_model(self, ctx):
            return ctx.model_copy(update={field: value})
    registry = DirectiveRegistry()
    registry.register(Escalate(name='bad', error_policy='continue'))
    with pytest.raises(DirectiveError):
        asyncio.run(registry.build(('bad',)).apply('before_model', context()))


@pytest.mark.parametrize('change', ['prompt', 'model', 'invalid', 'budget', 'memory'])
def test_model_copy_bypass_and_budget_rejected(change):
    class Corrupt(Directive):
        async def before_model(self, ctx):
            if change == 'memory':
                from uai_core.memory import WorkingMemory
                return ctx.model_copy(update={'working_memory': WorkingMemory()})
            updates = {'prompt': {'system_prompt': 'Override'}, 'model': {'model': 'other'},
                       'invalid': {'messages': ()},
                       'budget': {'messages': (Message(role='assistant', content='x' * 64000),)}}
            return ctx.model_copy(update={'model_input': ctx.model_input.model_copy(update=updates[change])})
    registry = DirectiveRegistry()
    registry.register(Corrupt(name='bad', error_policy='continue'))
    with pytest.raises(DirectiveError):
        asyncio.run(registry.build(('bad',)).apply('before_model', context()))


def test_timeout_error_policy_and_mandatory_fail_closed():
    class Slow(Directive):
        async def before_model(self, ctx):
            await asyncio.sleep(1)
            return ctx
    for mandatory, policy, fails in [(False, 'continue', False), (False, 'fail', True), (True, 'continue', True)]:
        registry = DirectiveRegistry()
        registry.register(Slow(name='slow', timeout_seconds=.001, error_policy=policy), mandatory=mandatory)
        operation = registry.build(('slow',)).apply('before_model', context())
        if fails:
            with pytest.raises(DirectiveError):
                asyncio.run(operation)
        else:
            assert asyncio.run(operation).authority.principal_id == 'caller'


def test_runtime_integration_before_after_and_failure():
    from test_capabilities import send, body, Provider
    from uai_runtime.app import create_app
    calls = []
    class Observe(Record):
        async def after_model(self, ctx):
            assert ctx.model_output == 'Ciao'
            calls.append('after')
            raise RuntimeError('secret plugin details')
    registry = DirectiveRegistry()
    registry.register(Observe(calls, name='observe'), mandatory=True)
    response = send(create_app('internal-secret', Provider(), directive_registry=registry),
                    '/internal/v1/runs', body())
    assert calls == ['observe', 'after']
    assert 'directive_failed' in response.text
    assert 'response.completed' not in response.text
    assert 'secret plugin details' not in response.text


def test_cancellation_propagates_and_timeout_cancels_callback():
    cancelled = []
    class Wait(Directive):
        async def before_model(self, ctx):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
    registry = DirectiveRegistry()
    registry.register(Wait(name='wait', timeout_seconds=10), mandatory=True)
    async def run():
        task = asyncio.create_task(registry.build().apply('before_model', context()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert cancelled == [True]


def test_after_model_cannot_rewrite_streamed_output():
    class Rewrite(Directive):
        async def after_model(self, ctx):
            return ctx.with_output('Forged')
    registry = DirectiveRegistry()
    registry.register(Rewrite(name='rewrite', error_policy='continue'))
    with pytest.raises(DirectiveError):
        asyncio.run(registry.build(('rewrite',)).apply('after_model', context().with_output('Original')))


def test_pipeline_snapshot_is_not_changed_by_later_registration():
    registry = DirectiveRegistry()
    snapshot = registry.build()
    registry.register(Directive(name='new'), mandatory=True)
    assert snapshot.names == ()
    assert registry.build().names == ('new',)


def test_full_history_still_completes_with_empty_pipeline():
    from test_capabilities import send, body, Provider
    from uai_runtime.app import create_app
    data = body()
    data['messages'] = [{'role': 'user', 'content': 'Hi'}] * 100
    response = send(create_app('internal-secret', Provider()), '/internal/v1/runs', data)
    assert 'response.completed' in response.text


def test_internal_assistant_selection_requires_registered_name():
    from test_capabilities import send, body, Provider, assistant_config
    from uai_runtime.app import create_app
    calls = []
    registry = DirectiveRegistry()
    registry.register(Record(calls, name='selected'))
    registry.register(Record(calls, name='unused'))
    app = create_app('internal-secret', Provider(), directive_registry=registry)
    data = body()
    data['system_prompt'] = 'Helpful'
    data['assistant'] = assistant_config()
    data['assistant']['directives'] = ['selected']
    response = send(app, '/internal/v1/runs', data)
    assert response.status_code == 200
    assert 'response.completed' in response.text
    assert calls == ['selected']
    data['assistant']['directives'] = ['unknown']
    response = send(app, '/internal/v1/runs', data)
    assert response.status_code == 422
    assert 'unknown_directive' in response.text


def test_authenticated_selection_validation_does_not_execute_callbacks():
    from test_capabilities import send
    from uai_runtime.app import create_app
    calls = []
    registry = DirectiveRegistry()
    registry.register(Record(calls, name='guard'), mandatory=True)
    registry.register(Record(calls, name='selected', depends_on=('guard',)))
    registry.register(Directive(name='missing', depends_on=('absent',)))
    registry.register(Directive(name='cycle-a', depends_on=('cycle-b',)))
    registry.register(Directive(name='cycle-b', depends_on=('cycle-a',)))
    app = create_app('internal-secret', object(), directive_registry=registry)
    path = '/internal/v1/directives/validate'
    assert send(app, path, {'directives': []}, authorized=False).status_code == 401
    for selected in [[], ['selected']]:
        response = send(app, path, {'directives': selected})
        assert response.status_code == 204
        assert response.content == b''
    for selected in [['unknown'], ['missing'], ['cycle-a', 'cycle-b'], ['selected', 'selected'],
                     ['bad name'], ['selected'] * 65]:
        assert send(app, path, {'directives': selected}).status_code == 422
    assert send(app, path, {'directives': [], 'python_module': 'evil'}).status_code == 422
    assert calls == []


def test_trusted_environment_factory_runs_the_docker_directive_fixture(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    from test_capabilities import send, body, assistant_config
    from uai_core.providers import ModelChunk

    class Echo:
        max_tokens = 1024

        async def stream(self, request):
            yield ModelChunk(text='Risposta mock: ' + request.messages[-1].content)

    trace = tmp_path / 'trace.jsonl'
    monkeypatch.setenv('UAI_E2E_TRACE_PATH', str(trace))
    monkeypatch.setenv('MODEL_NAME', 'test')
    monkeypatch.setenv('MODEL_BASE_URL', 'http://mock-provider/v1')
    monkeypatch.setenv('INTERNAL_API_KEY', 'internal-secret'.ljust(32, 'x'))
    monkeypatch.setattr('uai_runtime.app.OpenAIProvider', lambda *args, **kwargs: Echo())
    path = Path(__file__).resolve().parents[3] / 'tests/e2e/directive_runtime.py'
    spec = importlib.util.spec_from_file_location('directive_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = module.from_env()
    data = body()
    data['system_prompt'] = 'Helpful'
    data['assistant'] = assistant_config()
    data['assistant']['directives'] = ['e2e.prefix']

    async def post():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as client:
            return await client.post('/internal/v1/runs', json=data,
                                     headers={'Authorization': 'Bearer ' + 'internal-secret'.ljust(32, 'x')})

    response = asyncio.run(post())
    assert 'Risposta mock: E2E directive: Hi' in response.text
    assert 'response.completed' in response.text
    data['assistant']['directives'] = ['e2e.prefix', 'e2e.reject']
    response = asyncio.run(post())
    assert 'directive_failed' in response.text
    assert 'response.completed' not in response.text
    assert 'private fixture diagnostic' not in response.text

    import json
    observations = [json.loads(line) for line in trace.read_text().splitlines()]
    assert observations[-1]['event_type'] == 'agent.failed'
    assert any(item['event_type'] == 'response.completed' for item in observations)
    assert 'Risposta mock' not in trace.read_text()


def test_pipeline_accepts_reordered_frozenset_metadata():
    class Rewrite(Directive):
        async def before_model(self, ctx):
            return ctx.with_messages((Message(role='user', content='Changed'),))

    # JSON dumps order frozenset members by hash table layout. Find one scope set
    # whose order changes when the context is reconstructed, then prove the
    # pipeline still accepts it.
    for i in range(1000):
        scopes = frozenset(f'scope:{i}:{j}' for j in range(20))
        ctx = ExecutionContext.model_validate({
            **context().model_dump(),
            'authority': {'principal_id': 'caller', 'scopes': list(scopes)},
        })
        restored = ExecutionContext.model_validate({**ctx.model_dump(warnings=False),
                                                    'working_memory': ctx.working_memory})
        if (ctx.model_dump(mode='json', exclude={'model_input'})
                != restored.model_dump(mode='json', exclude={'model_input'})):
            break
    else:
        pytest.skip('interpreter serializes frozenset members deterministically')

    registry = DirectiveRegistry()
    registry.register(Rewrite(name='test.rewrite'))
    result = asyncio.run(registry.build(('test.rewrite',)).apply('before_model', ctx))
    assert result.model_input.messages == (Message(role='user', content='Changed'),)
