"""Single trusted registry and bounded, deny-by-default built-in invocation path."""
import asyncio
import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
from jsonschema import Draft202012Validator

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from uai_core.builtin.directives.tool_policy import ToolPolicyDirective
from uai_core.context import ExecutionContext
from uai_core.events import LifecycleEvent
from uai_core.tools import ToolDefinition, ToolExecutionError
from .hooks import HookRegistry

logger = logging.getLogger(__name__)
_json = TypeAdapter(JsonValue, config=ConfigDict(strict=True, allow_inf_nan=False))


@dataclass(frozen=True)
class _RegisteredTool:
    metadata: str
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    handler: Callable


class ToolRegistry:
    def __init__(self):
        self._entries: dict[str, _RegisteredTool] = {}

    def clone(self) -> "ToolRegistry":
        """Detach registration membership; existing executions retain their selection."""
        result = ToolRegistry()
        result._entries = self._entries.copy()
        return result


    def register(self, definition: ToolDefinition, *, input_model: type[BaseModel],
                 output_model: type[BaseModel], handler: Callable) -> None:
        if definition.id in self._entries or len(self._entries) >= 64:
            raise ValueError('duplicate_or_excess_tool')
        connector_permissions = {permission for permission in definition.permissions
                                 if permission.startswith('connector:')}
        if definition.executor == 'builtin':
            if connector_permissions:
                raise ValueError('connector_permission_not_allowed')
        elif len(connector_permissions) != 1:
            raise ValueError('connector_permission_required')
        elif definition.executor == 'http' and definition.risk_level != 'read_only':
            raise ValueError('mutating_http_tool_not_supported')
        if (not all(isinstance(model, type) and issubclass(model, BaseModel)
                    and model.model_config.get('extra') == 'forbid' for model in (input_model, output_model))
                or not inspect.iscoroutinefunction(handler)
                or definition.input_schema != input_model.model_json_schema()
                or definition.output_schema != output_model.model_json_schema()):
            raise ValueError('tool_schema_or_handler_mismatch')
        # A JSON snapshot detaches mutable schema dictionaries from host/catalog callers.
        metadata = ToolDefinition.model_validate_json(definition.model_dump_json()).model_dump_json()
        self._entries[definition.id] = _RegisteredTool(metadata, input_model, output_model, handler)

    def register_isolated(self, definition: ToolDefinition, *, handler: Callable) -> None:
        """Register a JSON-schema tool proxied to an isolated HTTP plugin."""
        if definition.id in self._entries or len(self._entries) >= 64:
            raise ValueError('duplicate_or_excess_tool')
        connectors = {permission for permission in definition.permissions
                      if permission.startswith('connector:')}
        if (definition.executor != 'isolated' or definition.risk_level != 'read_only'
                or len(connectors) != 1 or not inspect.iscoroutinefunction(handler)):
            raise ValueError('invalid_isolated_tool')
        for schema in (definition.input_schema, definition.output_schema):
            try:
                Draft202012Validator.check_schema(schema)
                encoded = json.dumps(schema, sort_keys=True, separators=(',', ':')).encode()
            except Exception:
                raise ValueError('invalid_isolated_schema') from None
            if schema.get('type') != 'object' or len(encoded) > 16384:
                raise ValueError('invalid_isolated_schema')
        metadata = ToolDefinition.model_validate_json(definition.model_dump_json()).model_dump_json()
        self._entries[definition.id] = _RegisteredTool(metadata, None, None, handler)

    def catalog(self) -> list[ToolDefinition]:
        return [ToolDefinition.model_validate_json(self._entries[key].metadata) for key in sorted(self._entries)]


def default_tool_registry() -> ToolRegistry:
    from uai_core.builtin.tools.text_stats import definition, text_stats, TextStatsInput, TextStatsOutput
    registry = ToolRegistry()
    registry.register(definition(), input_model=TextStatsInput, output_model=TextStatsOutput, handler=text_stats)
    return registry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, *, hook_registry: HookRegistry | None = None,
                 policy: ToolPolicyDirective | None = None):
        self._registry = registry
        self._hooks = hook_registry or HookRegistry()
        self._policy = policy or ToolPolicyDirective()

    def _authorize(self, context: ExecutionContext, definition: ToolDefinition) -> None:
        """Fail closed for every policy rejection or policy implementation error."""
        try:
            self._policy.authorize_tool(context, definition)
        except PermissionError as exc:
            code = exc.args[0] if exc.args and exc.args[0] in {'forbidden', 'approval_required'} else 'forbidden'
            raise ToolExecutionError(code) from None
        except Exception:
            raise ToolExecutionError('forbidden') from None

    async def execute(self, context: ExecutionContext, tool_id: str, arguments: JsonValue) -> JsonValue:
        hooks = self._hooks.snapshot()
        safe_id = tool_id if isinstance(tool_id, str) and re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', tool_id) else 'invalid'

        async def observe(kind, **payload):
            await hooks.emit(LifecycleEvent(event_type=kind, run_id=context.run_id,
                                            correlation_id=context.correlation_id,
                                            payload={'tool_id': safe_id, **payload}))

        async def fail(code):
            logger.warning('tool_failed tool_id=%s run_id=%s correlation_id=%s code=%s',
                           safe_id, context.run_id, context.correlation_id, code)
            await observe('tool.failed', code=code)

        try:
            await observe('tool.requested')
            if safe_id != tool_id or tool_id not in self._registry._entries:
                raise ToolExecutionError('unknown_tool')
            entry = self._registry._entries[tool_id]
            definition = ToolDefinition.model_validate_json(entry.metadata)
            self._authorize(context, definition)
            await observe('tool.authorized')
            try:
                raw = _json.validate_python(arguments, strict=True)
                encoded = _json.dump_json(raw)
                if len(encoded) > 131072 or len(encoded.decode()) > context.limits.max_input_chars:
                    raise ToolExecutionError('input_limit')
                if entry.input_model is None:
                    try:
                        Draft202012Validator(definition.input_schema).validate(raw)
                    except Exception:
                        raise ToolExecutionError('invalid_input') from None
                    params = raw
                    normalized = _json.dump_json(raw)
                else:
                    params = entry.input_model.model_validate_json(encoded, strict=True)
                    normalized = params.model_dump_json().encode()
                if len(normalized) > 131072 or len(normalized.decode()) > context.limits.max_input_chars:
                    raise ToolExecutionError('input_limit')
            except ToolExecutionError:
                raise
            except Exception:
                raise ToolExecutionError('invalid_input') from None
            # Approval waits and plugin changes can invalidate a grant after the
            # first check; never start the effect on a stale authorization.
            self._authorize(context, definition)
            await observe('tool.started')
            try:
                async with asyncio.timeout(min(definition.timeout, context.limits.duration_seconds)):
                    returned = await entry.handler(params)
            except ToolExecutionError:
                raise
            except TimeoutError:
                raise ToolExecutionError('tool_timeout') from None
            except Exception:
                raise ToolExecutionError('executor_error') from None
            try:
                raw = returned.model_dump(mode='json', warnings=False) if isinstance(returned, BaseModel) else returned
                raw = _json.validate_python(raw, strict=True)
                encoded = _json.dump_json(raw)
                if len(encoded) > 131072 or len(encoded.decode()) > context.limits.max_output_chars:
                    raise ToolExecutionError('output_limit')
                if entry.output_model is None:
                    try:
                        Draft202012Validator(definition.output_schema).validate(raw)
                    except Exception:
                        raise ToolExecutionError('invalid_output') from None
                    result = raw
                else:
                    # Revalidate plain data: a handler can return model_copy with invalid fields.
                    validated = entry.output_model.model_validate_json(encoded, strict=True)
                    result = _json.validate_python(validated.model_dump(mode='json'), strict=True)
                encoded = _json.dump_json(result)
                if len(encoded) > 131072 or len(encoded.decode()) > context.limits.max_output_chars:
                    raise ToolExecutionError('output_limit')
            except ToolExecutionError:
                raise
            except Exception:
                raise ToolExecutionError('invalid_output') from None
            await observe('tool.completed', output_chars=len(encoded.decode()))
            logger.info('tool_completed tool_id=%s run_id=%s correlation_id=%s',
                        safe_id, context.run_id, context.correlation_id)
            return result
        except ToolExecutionError as exc:
            await fail(exc.code)
            raise
        except asyncio.CancelledError:
            await fail('cancelled')
            raise
