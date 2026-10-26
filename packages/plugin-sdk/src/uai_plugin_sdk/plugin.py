"""Public plugin contracts. Lifecycle orchestration belongs to the host manager."""
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, JsonValue
from uai_core.directives import Directive
from uai_core.hooks import HookSubscriber
from uai_core.tools import ToolDefinition

from .manifest import PluginManifest
from .skills import Skill


class PluginRegistrar(Protocol):
    """Contributions only: no authority grant or removal of host security guards."""
    def add_directive(self, directive: Directive) -> None: ...
    def add_tool(self, definition: ToolDefinition, *, input_model: type[BaseModel],
                 output_model: type[BaseModel], handler: Callable[[BaseModel], Awaitable[BaseModel | JsonValue]]) -> None: ...
    def add_observer(self, subscriber: HookSubscriber) -> None: ...
    def add_skill(self, skill: Skill) -> None: ...


class PluginHealth(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    status: Literal['unknown', 'ok', 'degraded', 'unavailable'] = 'unknown'


class Plugin(ABC):
    def __init__(self, manifest: PluginManifest):
        self._manifest = manifest.validated_copy().model_dump_json()

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest.model_validate_json(self._manifest)

    @abstractmethod
    def register(self, registrar: PluginRegistrar) -> None:
        """Declare namespaced contributions to a host-controlled registrar."""

    async def prepare(self) -> None:
        """Optional bounded preparation before registration (e.g. remote catalog)."""

    async def activate(self, config: dict[str, JsonValue]) -> None:
        """Optional lifecycle hook; configuration is validated by the host manager."""

    async def deactivate(self) -> None:
        """Optional hook for resources owned by this plugin."""

    async def health(self) -> PluginHealth:
        return PluginHealth()
