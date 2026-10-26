"""Per-process run cancellation tokens and a cancel-aware event wrapper."""
import asyncio
from collections.abc import AsyncIterator

from uai_core.events import CancelledPayload, RuntimeEvent


class RunStateRegistry:
    def __init__(self):
        self._events: dict[str, asyncio.Event] = {}

    def register(self, run_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[run_id] = event
        return event

    def cancel(self, run_id: str) -> bool:
        event = self._events.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    def unregister(self, run_id: str) -> None:
        self._events.pop(run_id, None)


async def cancel_aware_events(events, registry: RunStateRegistry, run_id: str,
                              correlation_id, cancel_event: asyncio.Event) -> AsyncIterator[RuntimeEvent]:
    iterator = events.__aiter__()
    cancel_task = asyncio.create_task(cancel_event.wait())
    try:
        while True:
            next_task = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({next_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
            if cancel_task in done:
                next_task.cancel()
                try:
                    await next_task
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass
                yield RuntimeEvent(event_type='agent.cancelled',
                                   payload=CancelledPayload(code='cancelled'),
                                   run_id=run_id, correlation_id=correlation_id)
                return
            try:
                item = next_task.result()
            except StopAsyncIteration:
                return
            yield item
            if item.event_type in ('response.completed', 'agent.failed', 'agent.cancelled'):
                return
    finally:
        cancel_task.cancel()
        await asyncio.gather(cancel_task, return_exceptions=True)
        try:
            await iterator.aclose()
        finally:
            registry.unregister(run_id)


__all__ = ['RunStateRegistry', 'cancel_aware_events']
