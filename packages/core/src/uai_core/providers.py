"""Provider-neutral streaming protocol used by the agent and concrete adapters."""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from .models import ModelInput


class ProviderError(Exception):
    """Normalized provider failure; never forward private upstream diagnostics."""


@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    id: str = ''
    name: str = ''
    arguments: str = ''


@dataclass(frozen=True)
class ModelChunk:
    text: str = ''
    usage: dict[str, int] | None = None
    tool_calls: tuple[ToolCallDelta, ...] = ()


class ModelProvider(Protocol):
    def stream(self, request: ModelInput) -> AsyncIterator[ModelChunk]: ...
