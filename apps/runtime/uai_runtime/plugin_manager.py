"""Host-approved Python plugins. Trusted code runs in process, without a sandbox.

No discovery string, import path, installation, or authority grant is accepted here.
The host supplies installed instances and their approved Pydantic config models.
"""
import asyncio
import logging
from dataclasses import dataclass
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from uai_plugin_sdk.manifest import PluginID
from uai_core.directives import DirectiveRegistry
from uai_plugin_sdk.manifest import resolve_manifests
from uai_plugin_sdk.plugin import PluginHealth
from .hooks import HookRegistry
from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)
_json = TypeAdapter(JsonValue, config=ConfigDict(strict=True, allow_inf_nan=False))


class PluginSetting(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool
    config: dict[str, JsonValue]


class PluginConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(ge=1)
    settings: dict[PluginID, PluginSetting] = Field(max_length=64)


@dataclass(frozen=True)
class PluginSnapshot:
    directives: DirectiveRegistry
    tools: ToolRegistry
    hooks: HookRegistry
    skills: dict

    def clone(self):
        return PluginSnapshot(self.directives.clone(), self.tools.clone(), self.hooks.clone(), self.skills.copy())


class _Registrar:
    def __init__(self, manifest):
        self.manifest = manifest
        self.calls = []
        self.closed = False

    def _add(self, capability, name, value, kwargs=None):
        if self.closed:
            raise ValueError('plugin_registration_closed')
        if capability not in self.manifest.capabilities or not name.startswith(self.manifest.id + '.'):
            raise ValueError('plugin_namespace_or_capability')
        if len(self.calls) >= 64:
            raise ValueError('plugin_contribution_limit')
        self.calls.append((capability, value, kwargs or {}))

    def add_directive(self, directive):
        self._add('directives', directive.name, directive)

    def add_tool(self, definition, **kwargs):
        self._add('tools', definition.id, definition, kwargs)

    def add_observer(self, subscriber):
        self._add('hooks', subscriber.name, subscriber)

    def add_skill(self, skill):
        self._add('skills', skill.id, skill)

    def apply(self, snapshot):
        for kind, value, kwargs in self.calls:
            if kind == 'directives':
                snapshot.directives.register(value)
            elif kind == 'tools':
                if value.executor == 'isolated':
                    snapshot.tools.register_isolated(value, handler=kwargs['handler'])
                else:
                    snapshot.tools.register(value, **kwargs)
            elif kind == 'hooks':
                snapshot.hooks.register(value)
            else:
                if value.id in snapshot.skills or len(snapshot.skills) >= 64:
                    raise ValueError('duplicate_or_excess_skill')
                snapshot.skills[value.id] = value


class PluginManager:
    def __init__(self, approved, *, directives=None, tools=None, hooks=None):
        approved = list(approved)
        ordered = resolve_manifests(plugin.manifest for plugin, _ in approved)
        self._plugins = {plugin.manifest.id: (plugin, model) for plugin, model in approved}
        for _, model in approved:
            if not isinstance(model, type) or not issubclass(model, BaseModel) or model.model_config.get('extra') != 'forbid':
                raise ValueError('plugin_config_model_required')
        self._manifests = {item.id: item for item in ordered}
        for key, (_, model) in self._plugins.items():
            schema = self._manifests[key].config_schema
            if schema and schema != model.model_json_schema():
                raise ValueError('plugin_config_schema_mismatch')
        self._base = PluginSnapshot(directives or DirectiveRegistry(),
                                    tools or ToolRegistry(), hooks or HookRegistry(), {})
        self._active = {}
        self._status = {key: 'inactive' for key in self._plugins}
        self._lock = asyncio.Lock()
        self._executions = 0
        self._configs = {}
        self._target = None
        self._last_revision = 0
        self._last_requested = None
        self.applied_revision = 0

    def snapshot(self):
        return self._compose(self._active)

    @contextmanager
    def execution(self):
        """Pin one generation; lifecycle cleanup cannot close resources in use.

        The host runs this manager on one event loop. New executions fail fast
        during lifecycle mutations; administrators retry removal after runs drain.
        """
        if self._lock.locked():
            raise ValueError('plugin_lifecycle_busy')
        if self._target is not None and any(
                key not in self._target or not self._target[key]['enabled']
                or self._target[key]['config'] != self._configs[key] for key in self._active):
            raise ValueError('plugin_configuration_pending')
        self._executions += 1
        try:
            yield self.snapshot()
        finally:
            self._executions -= 1

    def catalog(self):
        return [{'manifest': item.model_dump(mode='json'), 'state': self._status[key]}
                for key, item in self._manifests.items()]

    def status(self):
        return self._status.copy()

    async def health(self, plugin_id):
        async with self._lock:
            if plugin_id not in self._active:
                return PluginHealth(status='unavailable')
            try:
                async with asyncio.timeout(5):
                    result = await self._plugins[plugin_id][0].health()
                return PluginHealth.model_validate(result.model_dump())
            except (Exception, asyncio.CancelledError) as exc:
                if isinstance(exc, asyncio.CancelledError) and asyncio.current_task().cancelling():
                    raise
                logger.warning('plugin_failed plugin_id=%s phase=health', plugin_id)
                return PluginHealth(status='unavailable')

    def _compose(self, active):
        snapshot = self._base.clone()
        for key in self._manifests:
            if key in active:
                active[key].apply(snapshot)
        return snapshot

    async def activate(self, plugin_id, config):
        async with self._lock:
            self._target = None
            self.applied_revision = 0
            return await self._activate(plugin_id, config)

    async def _activate(self, plugin_id, config):
        if plugin_id not in self._plugins or plugin_id in self._active:
            return False
        manifest = self._manifests[plugin_id]
        if any(dep.id not in self._active for dep in manifest.dependencies):
            return False
        plugin = self._plugins[plugin_id][0]
        started = False
        try:
            validated = self._validated_config(plugin_id, config)
            started = True
            async with asyncio.timeout(5):
                await plugin.prepare()
            registrar = _Registrar(manifest)
            plugin.register(registrar)
            registrar.calls = tuple(registrar.calls)
            registrar.closed = True
            proposed = {**self._active, plugin_id: registrar}
            self._compose(proposed)  # Validate all contributions before lifecycle side effects.
            config_snapshot = _json.validate_json(_json.dump_json(validated))
            async with asyncio.timeout(5):
                await plugin.activate(validated)
            # No await between publishing contributions and active membership.
            self._active = proposed
            self._status[plugin_id] = 'active'
            self._configs[plugin_id] = config_snapshot
            logger.info('plugin_activated plugin_id=%s', plugin_id)
            return True
        except (Exception, asyncio.CancelledError) as exc:
            self._status[plugin_id] = 'failed'
            logger.warning('plugin_failed plugin_id=%s phase=activate', plugin_id)
            if started:
                await self._cleanup(plugin_id)
            if isinstance(exc, asyncio.CancelledError) and asyncio.current_task().cancelling():
                raise
            return False

    async def _cleanup(self, plugin_id):
        try:
            async with asyncio.timeout(5):
                await self._plugins[plugin_id][0].deactivate()
            return True
        except (Exception, asyncio.CancelledError) as exc:
            if isinstance(exc, asyncio.CancelledError) and asyncio.current_task().cancelling():
                raise
            logger.warning('plugin_failed plugin_id=%s phase=deactivate', plugin_id)
            return False

    async def deactivate(self, plugin_id):
        async with self._lock:
            self._target = None
            self.applied_revision = 0
            return await self._deactivate(plugin_id)

    async def _deactivate(self, plugin_id):
        if plugin_id not in self._active or self._executions:
            return False
        if any(any(dep.id == plugin_id for dep in self._manifests[key].dependencies)
               for key in self._active):
            return False
        proposed = {key: value for key, value in self._active.items() if key != plugin_id}
        self._compose(proposed)
        self._active = proposed
        self._configs.pop(plugin_id, None)
        # Removal remains effective even when the plugin's cleanup fails.
        self._status[plugin_id] = 'inactive'
        try:
            if not await self._cleanup(plugin_id):
                self._status[plugin_id] = 'failed'
        except asyncio.CancelledError:
            self._status[plugin_id] = 'failed'
            raise
        if self._status[plugin_id] == 'inactive':
            logger.info('plugin_deactivated plugin_id=%s', plugin_id)
        return self._status[plugin_id] == 'inactive'

    def _validated_config(self, plugin_id, config):
        raw = _json.validate_python(config, strict=True)
        if len(_json.dump_json(raw)) > 32768:
            raise ValueError('plugin_config_limit')
        model = self._plugins[plugin_id][1]
        validated = _json.validate_python(model.model_validate(raw, strict=True).model_dump(mode='json'), strict=True)
        if len(_json.dump_json(validated)) > 32768:
            raise ValueError('plugin_config_limit')
        return validated

    def validate_configuration(self, settings):
        raw = PluginConfiguration.model_validate({'revision': 1, 'settings': settings}).model_dump()['settings']
        if not raw.keys() <= self._plugins.keys():
            raise ValueError('unknown_plugin')
        normalized = {}
        for key, setting in raw.items():
            validated = self._validated_config(key, setting['config'])
            normalized[key] = {'enabled': setting['enabled'], 'config': validated}
        for key, setting in normalized.items():
            if setting['enabled'] and any(not normalized.get(dep.id, {}).get('enabled', False)
                                          for dep in self._manifests[key].dependencies):
                raise ValueError('plugin_missing_enabled_dependency')
        return normalized

    async def reconcile(self, revision, settings):
        async with self._lock:
            target = self.validate_configuration(settings)
            if (revision < self._last_revision
                    or (revision == self._last_revision and self._last_requested != target)):
                return False
            self._last_revision, self._last_requested, self._target = revision, target, target
            changed = {key for key in self._active if key not in target or not target[key]['enabled']
                       or target[key]['config'] != self._configs[key]}
            # Configuring a dependency also drains/restarts its active dependents.
            for key in self._manifests:
                if key in self._active and any(dep.id in changed for dep in self._manifests[key].dependencies):
                    changed.add(key)
            if changed and self._executions:
                return False
            successful = True
            for key in reversed(self._manifests):
                if key in changed:
                    successful = await self._deactivate(key) and successful
            for key in self._manifests:
                if target.get(key, {}).get('enabled') and key not in self._active:
                    successful = await self._activate(key, target[key]['config']) and successful
            if successful:
                self.applied_revision = revision
            return successful


class PluginToolExecutor:
    """Use the same plugin generation for tool lookup, observers and cleanup pinning."""
    def __init__(self, manager: PluginManager, *, policy=None):
        self._manager = manager
        self._policy = policy

    async def execute(self, context, tool_id, arguments):
        from .tool_registry import ToolExecutor
        with self._manager.execution() as snapshot:
            return await ToolExecutor(snapshot.tools, hook_registry=snapshot.hooks,
                                      policy=self._policy).execute(context, tool_id, arguments)
