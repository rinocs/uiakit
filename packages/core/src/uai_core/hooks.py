"""Async observer registration metadata shared by runtime and trusted SDK."""
import math
import re
from dataclasses import dataclass
from collections.abc import Awaitable, Callable

from .events import LifecycleEvent, LifecycleEventType, LIFECYCLE_PAYLOADS


@dataclass(frozen=True)
class HookSubscriber:
    name: str
    callback: Callable[[LifecycleEvent], Awaitable[None]]
    priority: int = 0
    event_types: frozenset[LifecycleEventType] = frozenset(LIFECYCLE_PAYLOADS)
    timeout_seconds: float = .05

    def __post_init__(self):
        if (not re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', self.name)
                or not callable(self.callback) or not isinstance(self.priority, int)
                or not isinstance(self.event_types, frozenset)
                or not self.event_types <= LIFECYCLE_PAYLOADS.keys()
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise ValueError('invalid_hook_subscriber')

