"""Memory contracts. Persistent adapters must enforce gateway authorization."""
import json
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from .models import Message

_json_value = TypeAdapter(JsonValue)


class MemoryScope(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    principal_id: str = Field(min_length=1)
    conversation_id: UUID


class MemoryProvider(Protocol):
    """Authorized conversation storage, implemented at the persistence boundary.

    No default/no-op mutation adapter: a missing backend must remain unsupported.
    Retention deletes entries older than the supplied timezone-aware boundary.
    """
    async def read(self, scope: MemoryScope) -> tuple[Message, ...]: ...
    async def write(self, scope: MemoryScope, messages: tuple[Message, ...]) -> None: ...
    async def delete(self, scope: MemoryScope) -> None: ...
    async def retention(self, scope: MemoryScope, *, before: datetime) -> int: ...


class WorkingMemory:
    """Bounded per-execution JSON scratch space; never a source of authority."""
    def __init__(self, *, max_bytes: int = 64000):
        if max_bytes <= 0:
            raise ValueError('working_memory_limit')
        self._max_bytes = max_bytes
        self._values: dict[str, bytes] = {}
        self._size = 0

    def read(self, key: str) -> JsonValue | None:
        value = self._values.get(key)
        return json.loads(value) if value is not None else None

    def write(self, key: str, value: JsonValue) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError('invalid_working_memory_key')
        normalized = _json_value.validate_python(value)
        data = json.dumps(normalized, allow_nan=False, ensure_ascii=False,
                          separators=(',', ':')).encode('utf-8')
        old = self._values.get(key)
        size = self._size + len(data) - (len(old) if old is not None else 0)
        if old is None:
            size += len(key.encode('utf-8'))
        if size > self._max_bytes:
            raise ValueError('working_memory_limit')
        self._values[key] = data
        self._size = size

    def delete(self, key: str) -> None:
        old = self._values.pop(key, None)
        if old is not None:
            self._size -= len(old) + len(key.encode('utf-8'))

    def clear(self) -> None:
        self._values.clear()
        self._size = 0
