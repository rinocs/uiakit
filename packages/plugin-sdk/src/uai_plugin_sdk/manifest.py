"""Declarative metadata, not an authorization or package installation mechanism."""
import json
from graphlib import CycleError, TopologicalSorter
from importlib.metadata import version as installed_version
from collections.abc import Iterable
from typing import Annotated, Literal

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, field_validator, model_validator

PluginID = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$', max_length=200)]
ConnectorID = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.-]{0,99}$')]
Capability = Literal['tools', 'directives', 'hooks', 'skills']


def checked_version(value: str) -> str:
    try:
        Version(value)
    except InvalidVersion:
        raise ValueError('invalid_plugin_version') from None
    return value


def checked_specifier(value: str) -> str:
    try:
        SpecifierSet(value)
    except InvalidSpecifier:
        raise ValueError('invalid_version_specifier') from None
    return value


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Compatibility(FrozenModel):
    core: str = Field(min_length=1, max_length=200)
    _specifier = field_validator('core')(checked_specifier)


class PluginDependency(FrozenModel):
    id: PluginID
    version: str = Field(min_length=1, max_length=200)
    _specifier = field_validator('version')(checked_specifier)


class NetworkPermissions(FrozenModel):
    connectors: frozenset[ConnectorID] = Field(default_factory=frozenset, max_length=64)

    @field_serializer('connectors')
    def serialize_connectors(self, value):
        return sorted(value)


class PluginPermissions(FrozenModel):
    network: NetworkPermissions = Field(default_factory=NetworkPermissions)


class PluginManifest(FrozenModel):
    id: PluginID
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=50)
    runtime: Literal['python', 'isolated_http'] = 'python'
    compatibility: Compatibility
    capabilities: frozenset[Capability] = Field(default_factory=frozenset)
    dependencies: tuple[PluginDependency, ...] = Field(default=(), max_length=64)
    permissions: PluginPermissions = Field(default_factory=PluginPermissions)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    config_schema: dict[str, JsonValue] = Field(default_factory=dict)
    _version = field_validator('version')(checked_version)

    @field_serializer('capabilities')
    def serialize_capabilities(self, value):
        return sorted(value)

    @model_validator(mode='after')
    def validate_manifest(self):
        names = [item.id for item in self.dependencies]
        if len(names) != len(set(names)):
            raise ValueError('duplicate_plugin_dependency')
        # Native JSON validation and a small metadata budget; no schema execution.
        if len(json.dumps(self.model_dump(mode='json'), ensure_ascii=False,
                          allow_nan=False, separators=(',', ':')).encode()) > 32768:
            raise ValueError('plugin_manifest_limit')
        return self

    def validated_copy(self) -> 'PluginManifest':
        # Preserve NaN/type errors until validation; JSON serialization can turn
        # non-finite floats into null and hide a model_copy bypass.
        return PluginManifest.model_validate(self.model_dump(warnings=False))


def resolve_manifests(manifests: Iterable[PluginManifest], *, core_version: str | None = None) -> tuple[PluginManifest, ...]:
    """Resolve installed host metadata only; never import modules or grant scopes."""
    current = Version(core_version if core_version is not None else installed_version('uai-core'))
    entries = {}
    for source in manifests:
        item = source.validated_copy()
        if item.id in entries:
            raise ValueError('duplicate_plugin')
        if len(entries) >= 64:
            raise ValueError('plugin_count_limit')
        if current not in SpecifierSet(item.compatibility.core):
            raise ValueError('plugin_core_incompatible')
        entries[item.id] = item
    for item in entries.values():
        for dependency in item.dependencies:
            if dependency.id not in entries:
                raise ValueError('plugin_missing_dependency')
            if Version(entries[dependency.id].version) not in SpecifierSet(dependency.version):
                raise ValueError('plugin_dependency_incompatible')
    graph = {key: sorted(dep.id for dep in entries[key].dependencies) for key in sorted(entries)}
    try:
        order = tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        raise ValueError('plugin_dependency_cycle') from None
    return tuple(entries[key] for key in order)
