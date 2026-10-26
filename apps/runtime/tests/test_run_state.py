import asyncio
from uuid import uuid4

from uai_core.events import RuntimeEvent, StartedPayload, TextPayload
from uai_runtime.run_state import RunStateRegistry, cancel_aware_events


def event(kind, run_id, corr_id, payload=None):
    return RuntimeEvent(event_type=kind, run_id=run_id, correlation_id=corr_id,
                        payload=payload or {})


def test_registry_register_cancel_unregister():
    registry = RunStateRegistry()
    token = registry.register('run')
    assert registry.cancel('run') is True and token.is_set()
    assert registry.cancel('missing') is False
    registry.unregister('run')
    assert registry.cancel('run') is False


def test_normal_events_pass_through_and_unregister():
    registry = RunStateRegistry()
    run_id, corr_id = uuid4(), uuid4()
    token = registry.register(str(run_id))

    async def source():
        yield event('agent.started', run_id, corr_id)
        yield event('response.completed', run_id, corr_id, {'text': 'ok'})

    async def consume():
        return [item async for item in cancel_aware_events(
            source(), registry, str(run_id), corr_id, token)]

    items = asyncio.run(consume())
    assert [item.event_type for item in items] == ['agent.started', 'response.completed']
    assert registry.cancel(str(run_id)) is False


def test_cancel_during_stream_closes_source_and_emits_cancelled():
    registry = RunStateRegistry()
    run_id, corr_id = uuid4(), uuid4()
    token = registry.register(str(run_id))
    closed = []

    async def source():
        try:
            yield event('agent.started', run_id, corr_id)
            await asyncio.sleep(60)
            yield event('response.completed', run_id, corr_id, {'text': 'late'})
        finally:
            closed.append(True)

    async def consume():
        iterator = cancel_aware_events(source(), registry, str(run_id), corr_id, token)
        first = await anext(iterator)
        assert first.event_type == 'agent.started'
        registry.cancel(str(run_id))
        rest = [item async for item in iterator]
        return rest

    rest = asyncio.run(consume())
    assert [item.event_type for item in rest] == ['agent.cancelled']
    assert rest[0].payload.code == 'cancelled'
    assert closed == [True]
    assert registry.cancel(str(run_id)) is False


def test_cancel_before_iteration_yields_only_cancelled():
    registry = RunStateRegistry()
    run_id, corr_id = uuid4(), uuid4()
    token = registry.register(str(run_id))

    async def source():
        yield event('agent.started', run_id, corr_id)

    token.set()

    async def consume():
        return [item async for item in cancel_aware_events(
            source(), registry, str(run_id), corr_id, token)]

    items = asyncio.run(consume())
    assert [item.event_type for item in items] == ['agent.cancelled']
