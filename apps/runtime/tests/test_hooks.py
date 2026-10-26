import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from uai_core.events import LifecycleEvent, LIFECYCLE_PAYLOADS
from uai_runtime.hooks import HookRegistry, HookSubscriber


def event(kind='request.received', payload=None):
    return LifecycleEvent(event_type=kind, run_id=uuid4(), correlation_id=uuid4(),
                          payload=payload if payload is not None else {'message_count': 1, 'input_chars': 8})


def test_every_spec_phase_has_a_typed_payload_and_rejects_mismatches():
    from typing import get_args
    from uai_core.events import LifecycleEventType
    assert set(get_args(LifecycleEventType)) == set(LIFECYCLE_PAYLOADS)
    examples = {
        'request.received': {'message_count': 1, 'input_chars': 8},
        'request.authorized': {}, 'agent.started': {}, 'context.building': {},
        'context.ready': {'message_count': 1, 'input_chars': 8},
        'model.before': {'model': 'test'}, 'model.after': {'output_chars': 4},
        'tool.requested': {'tool_id': 'lookup'}, 'tool.authorized': {'tool_id': 'lookup'},
        'tool.started': {'tool_id': 'lookup'}, 'tool.completed': {'tool_id': 'lookup', 'output_chars': 4},
        'tool.failed': {'tool_id': 'lookup', 'code': 'tool_error'},
        'memory.read': {'scope': 'working', 'entries': 1},
        'memory.write': {'scope': 'working', 'entries': 1},
        'response.delta': {'characters': 4}, 'response.completed': {'characters': 4},
        'agent.failed': {'code': 'provider_error'}, 'agent.cancelled': {'reason': 'cancelled'},
    }
    assert set(examples) == set(LIFECYCLE_PAYLOADS)
    for kind, payload in examples.items():
        item = event(kind, payload)
        assert item.event_version == 1
        assert item.timestamp.utcoffset().total_seconds() == 0
        assert LifecycleEvent.model_validate_json(item.model_dump_json()) == item
        with pytest.raises(ValidationError):
            event(kind, {**payload, 'secret': 'never allowed'})
    with pytest.raises(ValidationError):
        event('response.delta', {'text': 'private'})
    with pytest.raises(ValidationError):
        event('model.before', {'code': 'wrong phase'})
    with pytest.raises(ValidationError):
        event('agent.failed', {'code': 'secret\nlog injection'})


def test_stable_order_filters_and_detached_immutable_snapshots():
    calls = []
    registry = HookRegistry()
    async def first(snapshot):
        calls.append('a')
        with pytest.raises(ValidationError):
            snapshot.run_id = uuid4()
        with pytest.raises(ValidationError):
            snapshot.payload.message_count = 999
        # Even bypassing frozen internals cannot affect later subscribers or the original event.
        object.__setattr__(snapshot.payload, 'message_count', 999)
    async def second(snapshot):
        calls.append('b')
        assert snapshot.payload.message_count == 1
        assert not hasattr(snapshot, 'authority')
        assert not hasattr(snapshot, 'working_memory')
    async def priority(snapshot):
        calls.append('priority')
    registry.register(HookSubscriber(name='z', callback=priority, priority=-1))
    registry.register(HookSubscriber(name='b', callback=second))
    registry.register(HookSubscriber(name='a', callback=first))
    registry.register(HookSubscriber(name='filtered', callback=second, event_types=frozenset({'model.after'})))
    original = event()
    asyncio.run(registry.snapshot().emit(original))
    assert calls == ['priority', 'a', 'b']
    assert original.payload.message_count == 1
    with pytest.raises(ValueError):
        registry.register(HookSubscriber(name='a', callback=first))


def test_observer_timeouts_errors_and_budget_are_isolated_and_audited(caplog):
    calls = []
    async def fail(snapshot):
        raise RuntimeError('secret prompt and API key')
    async def slow(snapshot):
        try:
            await asyncio.sleep(1)
        finally:
            calls.append('cancelled')
    async def record(snapshot):
        calls.append('recorded')
    registry = HookRegistry()
    registry.register(HookSubscriber(name='a', callback=fail))
    registry.register(HookSubscriber(name='b', callback=slow, timeout_seconds=.001))
    registry.register(HookSubscriber(name='c', callback=record))
    asyncio.run(registry.snapshot().emit(event()))
    assert calls == ['cancelled', 'recorded']
    assert 'error' in caplog.text and 'timeout' in caplog.text
    assert 'secret prompt' not in caplog.text
    assert 'correlation_id=' in caplog.text and 'run_id=' in caplog.text
    calls.clear()
    async def exhaust():
        dispatcher = registry.snapshot(budget_seconds=.001)
        await dispatcher.emit(event())
        await dispatcher.emit(event())
    asyncio.run(exhaust())
    assert 'recorded' not in calls
    assert 'budget' in caplog.text


def test_runtime_observes_lifecycle_without_changing_public_sse_or_leaking_content():
    from test_capabilities import send, body, Provider
    from uai_runtime.app import create_app
    received = []
    async def record(snapshot):
        received.append(snapshot)
    registry = HookRegistry()
    registry.register(HookSubscriber(name='capture', callback=record))
    data = body()
    data['messages'][0]['content'] = 'secret user message'
    data['system_prompt'] = 'secret operator prompt'
    response = send(create_app('internal-secret', Provider(), hook_registry=registry), '/internal/v1/runs', data)
    assert response.status_code == 200
    public = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert [e['event_type'] for e in public] == ['agent.started', 'response.delta', 'response.completed']
    assert [e.event_type for e in received] == [
        'request.received', 'request.authorized', 'agent.started', 'context.building',
        'context.ready', 'model.before', 'response.delta', 'model.after', 'response.completed']
    assert all(str(e.run_id) == data['run_id'] and str(e.correlation_id) == data['correlation_id'] for e in received)
    assert len({e.event_id for e in received}) == len(received)
    for e in public:
        assert next(o for o in received if str(o.event_id) == e['event_id']).event_type == e['event_type']
    serialized = ''.join(e.model_dump_json() for e in received)
    assert all(secret not in serialized for secret in ['secret user', 'secret operator', 'Ciao', 'internal-secret'])


def test_required_directive_failure_is_observed_and_stops_provider():
    from test_capabilities import send, body
    from uai_runtime.app import create_app
    from uai_core.directives import Directive, DirectiveRegistry
    kinds = []
    class Guard(Directive):
        async def before_model(self, context):
            raise RuntimeError('private policy detail')
    class Never:
        async def stream(self, request):
            pytest.fail('guard bypassed')
            yield
    async def observe(snapshot):
        kinds.append(snapshot.event_type)
    hooks = HookRegistry()
    hooks.register(HookSubscriber(name='observe', callback=observe))
    directives = DirectiveRegistry()
    directives.register(Guard(name='guard', error_policy='continue'), mandatory=True)
    response = send(create_app('internal-secret', Never(), hook_registry=hooks, directive_registry=directives),
                    '/internal/v1/runs', body())
    assert kinds[-1] == 'agent.failed'
    assert 'model.before' not in kinds and 'response.completed' not in kinds
    assert 'directive_failed' in response.text and 'private policy detail' not in response.text


def test_closing_execution_observes_cancellation():
    from uai_runtime.agent import BasicAgent
    from test_context import context
    from test_capabilities import Provider
    from uai_core.capabilities import ModelDefinition
    received = []
    async def observe(snapshot):
        received.append(snapshot.event_type)
    hooks = HookRegistry()
    hooks.register(HookSubscriber(name='observe', callback=observe))
    ctx = context()
    ctx.working_memory.write('private', 'run state')
    definition = ModelDefinition(id='test', capabilities={'chat', 'streaming'})
    agent = BasicAgent(Provider(), model_definition=definition, hook_registry=hooks)
    async def run():
        stream = agent.run(ctx)
        await anext(stream)
        await stream.aclose()
    asyncio.run(run())
    assert received[-1] == 'agent.cancelled'


def test_caller_cancellation_propagates_through_subscriber_and_clears_run_memory():
    from uai_core.agent import AgentRuntime
    from uai_core.capabilities import ModelDefinition
    from uai_core.directives import Directive, DirectiveRegistry
    from uai_runtime.agent import BasicAgent
    from test_context import context
    from test_capabilities import Provider
    reached = asyncio.Event()
    captured = []
    observed = []
    class Remember(Directive):
        async def before_model(self, ctx):
            ctx.working_memory.write('private', 'secret')
            captured.append(ctx)
            return ctx
    async def block(snapshot):
        observed.append(snapshot.event_type)
        if snapshot.event_type == 'model.before':
            reached.set()
            await asyncio.Event().wait()
    hooks = HookRegistry()
    hooks.register(HookSubscriber(name='block', callback=block, timeout_seconds=10))
    directives = DirectiveRegistry()
    directives.register(Remember(name='remember'), mandatory=True)
    definition = ModelDefinition(id='test', capabilities={'chat', 'streaming'})
    runtime = AgentRuntime(BasicAgent(Provider(), model_definition=definition,
                                     hook_registry=hooks, directive_registry=directives))
    ctx = context()
    async def run():
        async def consume():
            async for _ in runtime.run(run_id=ctx.run_id, correlation_id=ctx.correlation_id,
                                       authority=ctx.authority, limits=ctx.limits,
                                       model_input=ctx.model_input):
                pass
        task = asyncio.create_task(consume())
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert observed[-1] == 'agent.cancelled'
    assert captured[0].working_memory.read('private') is None


def test_observer_failure_does_not_change_success_and_terminal_timeout_is_isolated(caplog):
    from test_capabilities import send, body, Provider
    from uai_runtime.app import create_app
    observed = []
    async def broken(snapshot):
        if snapshot.event_type == 'response.completed':
            await asyncio.sleep(1)
        raise ValueError('secret credentials')
    async def record(snapshot):
        observed.append(snapshot.event_type)
    registry = HookRegistry()
    registry.register(HookSubscriber(name='broken', callback=broken, timeout_seconds=.001))
    registry.register(HookSubscriber(name='record', callback=record))
    response = send(create_app('internal-secret', Provider(), hook_registry=registry), '/internal/v1/runs', body())
    assert 'response.completed' in response.text and 'agent.failed' not in response.text
    assert observed[-1] == 'response.completed'
    assert 'secret credentials' not in caplog.text


def test_observer_self_cancel_is_isolated_and_registry_snapshot_is_per_run(caplog):
    calls = []
    async def self_cancel(snapshot):
        raise asyncio.CancelledError()
    async def record(snapshot):
        calls.append('record')
    registry = HookRegistry()
    registry.register(HookSubscriber(name='a', callback=self_cancel))
    old = registry.snapshot()
    registry.register(HookSubscriber(name='b', callback=record))
    asyncio.run(old.emit(event()))
    assert calls == []
    asyncio.run(registry.snapshot().emit(event()))
    assert calls == ['record'] and 'subscriber_cancelled' in caplog.text


def test_rejected_http_request_does_not_invent_an_authorized_run_trace():
    from test_capabilities import send, body, Provider
    from uai_runtime.app import create_app
    observed = []
    async def record(snapshot):
        observed.append(snapshot)
    registry = HookRegistry()
    registry.register(HookSubscriber(name='record', callback=record))
    app = create_app('internal-secret', Provider(), hook_registry=registry)
    assert send(app, '/internal/v1/runs', body(), authorized=False).status_code == 401
    invalid = body()
    invalid['model'] = 'unsupported'
    assert send(app, '/internal/v1/runs', invalid).status_code == 422
    assert observed == []


def test_closing_after_delta_closes_suspended_provider_before_returning():
    from uai_runtime.agent import BasicAgent
    from uai_core.capabilities import ModelDefinition
    from uai_core.providers import ModelChunk
    from test_context import context
    closed = []
    class Provider:
        async def stream(self, request):
            try:
                yield ModelChunk(text='private output')
                await asyncio.Event().wait()
            finally:
                closed.append(True)
    agent = BasicAgent(Provider(), model_definition=ModelDefinition(id='test', capabilities={'chat', 'streaming'}))
    async def run():
        stream = agent.run(context())
        assert (await anext(stream)).event_type == 'agent.started'
        assert (await anext(stream)).event_type == 'response.delta'
        await stream.aclose()
        assert closed == [True]
    asyncio.run(run())
