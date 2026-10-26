"""Bounded multi-step tool loop with provider-native tool calls and untrusted results."""
import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from uai_core.telemetry import get_telemetry
from uai_core.builtin.directives import install_builtin_directives
from uai_core.context import ExecutionContext
from uai_core.directives import DirectiveError, DirectiveRegistry
from uai_core.events import LifecycleEvent, RuntimeEvent, RuntimeEventType
from uai_core.providers import ModelProvider, ProviderError
from uai_core.tools import ToolDefinition, ToolExecutionError

from .hooks import HookRegistry
from .budgets import BudgetExceeded, RunBudget
from .audit import AuditLog
from .token_usage import UsageAccumulator
from .tool_executor import DurableToolRunner, ExecutionJournal, build_execution_request

class _OutputLimit(Exception):
    pass


class _ToolLoopError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _reject_constant(value: str):
    raise ValueError('non_finite_tool_arguments')


def _available_tools(context: ExecutionContext, catalog: list[ToolDefinition]) -> dict[str, ToolDefinition]:
    assistant = context.assistant
    if assistant is None:
        return {}
    allowed = {}
    for definition in catalog:
        connectors = {permission for permission in definition.permissions
                      if permission.startswith('connector:')}
        required = (definition.permissions - connectors) | {'tools:execute'}
        if (definition.id in assistant.tools and definition.id in context.authority.allowed_tool_ids
                and required <= context.authority.scopes and definition.risk_level == 'read_only'
                and definition.executor in ('builtin', 'http')):
            allowed[definition.id] = definition
    return allowed


def _tool_specs(tools: dict[str, ToolDefinition]) -> list[dict]:
    return [{'type': 'function',
             'function': {'name': definition.id, 'description': definition.description,
                          'parameters': definition.input_schema}}
            for definition in tools.values()]


class ToolCallingAgent:
    def __init__(self, provider: ModelProvider, *, model_definition, directive_registry: DirectiveRegistry | None = None,
                 hook_registry: HookRegistry | None = None, tool_executor=None,
                 tool_catalog: Callable[[], list[ToolDefinition]] | None = None,
                 execution_journal: ExecutionJournal | None = None,
                 audit_log: AuditLog | None = None):
        self.provider = provider
        self.model_definition = model_definition
        self.directive_registry = directive_registry or DirectiveRegistry()
        install_builtin_directives(self.directive_registry)
        self.hook_registry = hook_registry or HookRegistry()
        self.tool_executor = tool_executor
        self.tool_catalog = tool_catalog
        self.execution_journal = execution_journal
        self.audit_log = audit_log

    def run(self, context: ExecutionContext) -> AsyncIterator[RuntimeEvent]:
        body = context.model_input
        self.model_definition.require('chat', 'streaming', 'tool_calling')
        if context.assistant.structured_output is not None:
            self.model_definition.require('structured_output')
        if body.model != self.model_definition.id:
            raise ValueError('unsupported_model')
        if context.assistant is None or not context.assistant.tools:
            raise ValueError('tools_required')
        if self.tool_executor is None or self.tool_catalog is None:
            raise ValueError('tools_unavailable')
        if sum(len(m.content) for m in body.messages) + len(body.system_prompt) > context.limits.max_input_chars:
            raise ValueError('context_limit')
        pipeline = self.directive_registry.build(context.assistant.directives)
        available = _available_tools(context, self.tool_catalog())
        if not available:
            raise ValueError('tools_unavailable')
        return self._execute(context, pipeline, self.hook_registry.snapshot(), available)

    async def _execute(self, context: ExecutionContext, pipeline, hooks, available) -> AsyncIterator[RuntimeEvent]:
        def event(kind: RuntimeEventType, payload: dict) -> RuntimeEvent:
            return RuntimeEvent(event_type=kind, run_id=context.run_id,
                                correlation_id=context.correlation_id, payload=payload)

        async def observe(kind, payload):
            await hooks.emit(LifecycleEvent(event_type=kind, run_id=context.run_id,
                                            correlation_id=context.correlation_id, payload=payload))

        async def observed_event(kind, payload):
            item = event(kind, payload)
            await hooks.emit(LifecycleEvent.from_runtime(item))
            return item

        started = event('agent.started', {})
        terminal = False
        text = ''
        usage = UsageAccumulator()
        try:
            yield started
            try:
                async with asyncio.timeout(context.limits.duration_seconds):
                    await hooks.emit(LifecycleEvent.from_runtime(started))
                    await observe('request.received', {
                        'message_count': len(context.model_input.messages),
                        'input_chars': sum(len(m.content) for m in context.model_input.messages)
                                       + len(context.model_input.system_prompt)})
                    await observe('request.authorized', {})
                    await observe('context.building', {})
                    context = await pipeline.apply('before_model', context)
                    await observe('context.ready', {
                        'message_count': len(context.model_input.messages),
                        'input_chars': sum(len(m.content) for m in context.model_input.messages)
                                       + len(context.model_input.system_prompt)})
                    raw_messages = [{'role': 'system', 'content': context.model_input.system_prompt}]
                    raw_messages += [m.model_dump() for m in context.model_input.messages]
                    specs = _tool_specs(available)
                    budget = RunBudget.from_limits(context.limits, context.model_definition or self.model_definition)
                    for step in range(16):
                        budget.start_step()
                        budget.check_context(
                            json.dumps(raw_messages, sort_keys=True),
                            json.dumps(specs, sort_keys=True),
                            json.dumps(context.assistant.structured_output, sort_keys=True)
                            if context.assistant.structured_output else '')
                        await observe('model.before', {'model': context.model_input.model})
                        turn_text = ''
                        deltas: dict[int, dict] = {}
                        request = context.model_input.model_copy(update={
                            'provider_messages': tuple(raw_messages), 'tools': tuple(specs),
                            'structured_output': context.assistant.structured_output})
                        provider_span = get_telemetry('uai-runtime').tracer
                        provider_span = provider_span.start_span('provider.stream', attributes={
                            'run_id': str(context.run_id), 'model': context.model_input.model,
                        }) if provider_span is not None else None
                        upstream = self.provider.stream(request)
                        try:
                            async for chunk in upstream:
                                if chunk.usage is not None:
                                    usage.record_usage(chunk.usage)
                                if chunk.text:
                                    if len(text) + len(turn_text) + len(chunk.text) > context.limits.max_output_chars:
                                        raise _OutputLimit
                                    turn_text += chunk.text
                                    yield await observed_event('response.delta', {'text': chunk.text})
                                for delta in chunk.tool_calls:
                                    entry = deltas.setdefault(delta.index, {'id': '', 'name': '', 'arguments': ''})
                                    if delta.id:
                                        if entry['id'] and entry['id'] != delta.id:
                                            raise _ToolLoopError('tool_call_invalid')
                                        entry['id'] = delta.id
                                    if delta.name:
                                        entry['name'] += delta.name
                                    entry['arguments'] += delta.arguments
                        finally:
                            close = getattr(upstream, 'aclose', None)
                            if close is not None:
                                await close()
                            if provider_span is not None:
                                provider_span.end()
                        text += turn_text
                        usage.record_text(turn_text)
                        budget.check_tokens(usage)
                        await observe('model.after', {'output_chars': len(turn_text)})
                        if not deltas:
                            if not turn_text and not text:
                                raise ProviderError('empty_output')
                            break
                        calls = self._parse_calls(deltas, available)
                        budget.consume_tool_calls(len(calls))
                        raw_messages.append({
                            'role': 'assistant', 'content': turn_text or None,
                            'tool_calls': [{'id': call['id'], 'type': 'function',
                                            'function': {'name': call['name'],
                                                         'arguments': call['arguments']}}
                                           for call in calls]})
                        for call in calls:
                            result = await self._run_tool(context, available[call['name']], call)
                            raw_messages.append({'role': 'tool', 'tool_call_id': call['id'],
                                                 'content': _json_text(result)})
                    else:
                        raise _ToolLoopError('step_limit')
                    if not text:
                        raise ProviderError('empty_output')
                    await pipeline.apply('after_model', context.with_output(text))
                    citations = context.working_memory.read('citations')
                result = event('response.completed', {'text': text, 'usage': usage.value(),
                                                       'citations': citations if isinstance(citations, list) else []})
            except _OutputLimit:
                result = event('agent.failed', {'code': 'output_limit'})
            except _ToolLoopError as exc:
                result = event('agent.failed', {'code': exc.code})
            except ToolExecutionError:
                result = event('agent.failed', {'code': 'tool_failed'})
            except DirectiveError:
                result = event('agent.failed', {'code': 'directive_failed'})
            except TimeoutError:
                result = event('agent.failed', {'code': 'execution_timeout'})
            except ProviderError:
                result = event('agent.failed', {'code': 'provider_error'})
            except BudgetExceeded as exc:
                result = event('agent.failed', {'code': exc.code})
            await hooks.emit(LifecycleEvent.from_runtime(result))
            terminal = True
            yield result
        except (asyncio.CancelledError, GeneratorExit):
            if not terminal:
                await observe('agent.cancelled', {'reason': 'cancelled'})
            raise

    def _parse_calls(self, deltas: dict[int, dict], available: dict[str, ToolDefinition]) -> list[dict]:
        calls = []
        for index in sorted(deltas):
            entry = deltas[index]
            if not entry['id'] or not entry['name']:
                raise _ToolLoopError('tool_call_invalid')
            if entry['name'] not in available:
                raise _ToolLoopError('tool_not_authorized')
            arguments = entry['arguments'] or '{}'
            try:
                parsed = json.loads(arguments, parse_constant=_reject_constant)
            except (TypeError, ValueError):
                raise _ToolLoopError('tool_call_invalid') from None
            if not isinstance(parsed, dict):
                raise _ToolLoopError('tool_call_invalid')
            calls.append({'id': entry['id'], 'name': entry['name'],
                          'arguments': arguments, 'parsed': parsed})
        if not calls:
            raise _ToolLoopError('tool_call_invalid')
        return calls

    async def _run_tool(self, context: ExecutionContext, definition: ToolDefinition, call: dict):
        telemetry = get_telemetry('uai-runtime')
        with telemetry.span('tool.execute', {
            'run_id': str(context.run_id),
            'tool_id': definition.id,
            'risk_level': definition.risk_level,
            'executor': definition.executor,
        }):
            return await self._run_tool_inner(context, definition, call)

    async def _run_tool_inner(self, context: ExecutionContext, definition: ToolDefinition, call: dict):
        async def invoke():
            return await self.tool_executor.execute(context, call['name'], call['parsed'])

        if self.execution_journal is None:
            return await invoke()
        request = build_execution_request(context, definition, call['parsed'],
                                          tool_call_id=call['id'])
        return await DurableToolRunner(self.execution_journal, self.audit_log).run(request, invoke)


def _json_text(value) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise _ToolLoopError('tool_result_invalid') from None
