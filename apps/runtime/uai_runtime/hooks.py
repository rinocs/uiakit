"""Host-owned async observers; context modification belongs to directives."""
import asyncio
import logging
import math
from time import monotonic

from uai_core.events import LifecycleEvent
from uai_core.hooks import HookSubscriber

logger = logging.getLogger(__name__)




class HookRegistry:
    def __init__(self):
        self._subscribers: dict[str, HookSubscriber] = {}

    def clone(self) -> "HookRegistry":
        """Detach registration membership; existing executions retain their selection."""
        result = HookRegistry()
        result._subscribers = self._subscribers.copy()
        return result


    def register(self, subscriber: HookSubscriber) -> None:
        if subscriber.name in self._subscribers or len(self._subscribers) >= 64:
            raise ValueError('duplicate_or_excess_hook_subscriber')
        self._subscribers[subscriber.name] = subscriber

    def snapshot(self, *, budget_seconds: float = 1) -> 'HookDispatcher':
        if not math.isfinite(budget_seconds) or budget_seconds <= 0:
            raise ValueError('invalid_hook_budget')
        return HookDispatcher(tuple(sorted(self._subscribers.values(), key=lambda s: (s.priority, s.name))),
                              budget_seconds)


class HookDispatcher:
    """A fresh observer selection and elapsed-time budget for each execution."""
    def __init__(self, subscribers: tuple[HookSubscriber, ...], budget_seconds: float):
        self._subscribers = subscribers
        self._remaining = budget_seconds
        self._exhaustion_logged = False

    @staticmethod
    def _audit(event: LifecycleEvent, name: str, reason: str):
        # Exception text, response text and credentials are deliberately excluded.
        logger.warning('hook_failed subscriber=%s event_type=%s run_id=%s correlation_id=%s reason=%s',
                       name, event.event_type, event.run_id, event.correlation_id, reason)

    async def emit(self, event: LifecycleEvent) -> None:
        for subscriber in self._subscribers:
            if event.event_type not in subscriber.event_types:
                continue
            if self._remaining <= 0:
                if not self._exhaustion_logged:
                    self._audit(event, subscriber.name, 'budget_exhausted')
                    self._exhaustion_logged = True
                return
            start = monotonic()
            try:
                # Each subscriber owns a detached copy, including the nested payload.
                snapshot = LifecycleEvent.model_validate(event.model_dump())
                async with asyncio.timeout(min(self._remaining, subscriber.timeout_seconds)):
                    await subscriber.callback(snapshot)
            except TimeoutError:
                self._audit(event, subscriber.name, 'timeout')
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                self._audit(event, subscriber.name, 'subscriber_cancelled')
            except Exception:
                self._audit(event, subscriber.name, 'error')
            finally:
                self._remaining -= monotonic() - start
