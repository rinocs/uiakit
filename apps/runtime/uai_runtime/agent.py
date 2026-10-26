"""Single-model agent lifecycle, independent of HTTP and persistence."""
import asyncio
import json
from collections.abc import AsyncIterator

from uai_core.capabilities import ModelDefinition
from uai_core.builtin.directives import install_builtin_directives
from uai_core.context import ExecutionContext
from uai_core.directives import DirectiveRegistry, DirectiveError
from uai_core.events import LifecycleEvent, RuntimeEvent, RuntimeEventType
from uai_core.providers import ModelProvider, ProviderError
from uai_core.telemetry import get_telemetry

from .hooks import HookRegistry
from .budgets import BudgetExceeded, RunBudget
from .token_usage import UsageAccumulator


class _OutputLimit(Exception):
    pass


class BasicAgent:
    def __init__(self, provider: ModelProvider, *, model_definition: ModelDefinition,
                 directive_registry: DirectiveRegistry | None = None,
                 hook_registry: HookRegistry | None = None):
        self.provider = provider
        self.model_definition = model_definition
        self.directive_registry = directive_registry or DirectiveRegistry()
        install_builtin_directives(self.directive_registry)
        self.hook_registry = hook_registry or HookRegistry()

    def run(self, context: ExecutionContext) -> AsyncIterator[RuntimeEvent]:
        """Validate the authorized model input before HTTP streaming starts."""
        body = context.model_input
        if context.assistant is not None and context.assistant.tools:
            raise ValueError('tools_disabled')
        self.model_definition.require("chat", "streaming")
        if context.assistant is not None and context.assistant.structured_output is not None:
            self.model_definition.require("structured_output")
        if body.model != self.model_definition.id:
            raise ValueError('unsupported_model')
        if sum(len(m.content) for m in body.messages) + len(body.system_prompt) > context.limits.max_input_chars:
            raise ValueError('context_limit')
        pipeline = self.directive_registry.build(context.assistant.directives if context.assistant else ())
        return self._execute(context, pipeline, self.hook_registry.snapshot())

    async def _execute(self, context: ExecutionContext, pipeline, hooks) -> AsyncIterator[RuntimeEvent]:
        def event(kind: RuntimeEventType, payload: dict) -> RuntimeEvent:
            return RuntimeEvent(event_type=kind, run_id=context.run_id,
                                correlation_id=context.correlation_id, payload=payload)

        def observation(kind, payload):
            return LifecycleEvent(event_type=kind, run_id=context.run_id,
                                  correlation_id=context.correlation_id, payload=payload)

        async def observed_event(kind, payload):
            item = event(kind, payload)
            await hooks.emit(LifecycleEvent.from_runtime(item))
            return item

        metrics = {'message_count': len(context.model_input.messages),
                   'input_chars': sum(len(m.content) for m in context.model_input.messages)
                                  + len(context.model_input.system_prompt)}
        # These observations describe the accepted run, after HTTP authorization
        # and preflight. No run IDs are invented for rejected HTTP requests.
        received = observation('request.received', metrics)
        authorized = observation('request.authorized', {})
        started = event('agent.started', {})
        terminal = False
        text = ''
        usage = UsageAccumulator()
        try:
            # Preserve the public v1 first frame even for very short deadlines.
            yield started
            try:
                async with asyncio.timeout(context.limits.duration_seconds):
                    await hooks.emit(received)
                    await hooks.emit(authorized)
                    await hooks.emit(LifecycleEvent.from_runtime(started))
                    await hooks.emit(observation('context.building', {}))
                    context = await pipeline.apply('before_model', context)
                    budget = RunBudget.from_limits(context.limits, context.model_definition or self.model_definition)
                    budget.start_step()
                    budget.check_context(
                        context.model_input.system_prompt,
                        *(message.content for message in context.model_input.messages),
                        json.dumps(context.assistant.structured_output, sort_keys=True)
                        if context.assistant is not None and context.assistant.structured_output else '')
                    await hooks.emit(observation('context.ready', {
                        'message_count': len(context.model_input.messages),
                        'input_chars': sum(len(m.content) for m in context.model_input.messages)
                                       + len(context.model_input.system_prompt)}))
                    await hooks.emit(observation('model.before', {'model': context.model_input.model}))
                    model_input = context.model_input
                    if context.assistant is not None and context.assistant.structured_output is not None:
                        model_input = model_input.model_copy(
                            update={'structured_output': context.assistant.structured_output})
                    provider_span = get_telemetry('uai-runtime').tracer
                    provider_span = provider_span.start_span('provider.stream', attributes={
                        'run_id': str(context.run_id), 'model': context.model_input.model,
                    }) if provider_span is not None else None
                    upstream = self.provider.stream(model_input)
                    try:
                        async for chunk in upstream:
                            if chunk.usage is not None:
                                usage.record_usage(chunk.usage)
                            if chunk.text:
                                if len(text) + len(chunk.text) > context.limits.max_output_chars:
                                    raise _OutputLimit
                                text += chunk.text
                                yield await observed_event('response.delta', {'text': chunk.text})
                    finally:
                        close = getattr(upstream, 'aclose', None)
                        if close is not None:
                            await close()
                        if provider_span is not None:
                            provider_span.end()
                    if not text:
                        raise ProviderError('empty_output')
                    usage.record_text(text)
                    budget.check_tokens(usage)
                    await hooks.emit(observation('model.after', {'output_chars': len(text)}))
                    # after_model validates output; SSE deltas are immutable.
                    await pipeline.apply('after_model', context.with_output(text))
                citations = context.working_memory.read('citations')
                result = event('response.completed', {'text': text, 'usage': usage.value(),
                                                       'citations': citations if isinstance(citations, list) else []})
            except _OutputLimit:
                result = event('agent.failed', {'code': 'output_limit'})
            except DirectiveError:
                result = event('agent.failed', {'code': 'directive_failed'})
            except TimeoutError:
                result = event('agent.failed', {'code': 'execution_timeout'})
            except ProviderError:
                result = event('agent.failed', {'code': 'provider_error'})
            except BudgetExceeded as exc:
                result = event('agent.failed', {'code': exc.code})
            # A terminal observation is outside the execution timeout: a timeout
            # during notification must never produce a second terminal event.
            await hooks.emit(LifecycleEvent.from_runtime(result))
            terminal = True
            yield result
        except (asyncio.CancelledError, GeneratorExit) as exc:
            if not terminal:
                await hooks.emit(observation('agent.cancelled', {
                    'reason': 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'closed'}))
            raise
        # Cancellation propagates; AgentRuntime owns closing and memory cleanup.
