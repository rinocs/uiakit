import asyncio
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from uai_core.capabilities import ModelDefinition
from uai_core.configuration import AssistantConfig, ExecutionLimits
from uai_core.context import ExecutionAuthority, ExecutionContext
from uai_core.models import Message, ModelInput
from uai_core.providers import ModelChunk, ProviderError, ToolCallDelta
from uai_core.tools import ToolDefinition
from uai_runtime.agent import BasicAgent
from uai_runtime.budgets import BudgetExceeded, RunBudget
from uai_runtime.token_usage import UsageAccumulator
from uai_runtime.tool_loop import ToolCallingAgent
from uai_runtime.tool_registry import ToolExecutor, ToolRegistry


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(max_length=1000)


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    characters: int = Field(ge=0)


def definition():
    return ToolDefinition(id='test.count', name='Count', description='Counts', version='1.0.0',
                          input_schema=Input.model_json_schema(), output_schema=Output.model_json_schema(),
                          permissions={'tools:execute'}, risk_level='read_only')


def registry(calls):
    async def count(params):
        calls.append(params.text)
        return Output(characters=len(params.text))
    tools = ToolRegistry()
    tools.register(definition(), input_model=Input, output_model=Output, handler=count)
    return tools


def context(*, limits=None, capabilities=('chat', 'streaming', 'tool_calling'),
            tools=('test.count',), structured_output=None, context_window=None, max_output_tokens=None):
    config = AssistantConfig(id=uuid4(), version=1, name='Test', model='test', system_prompt='Helpful',
                             tools=tools, structured_output=structured_output)
    model = ModelDefinition(id='test', capabilities=set(capabilities),
                            context_window=context_window, max_output_tokens=max_output_tokens)
    return ExecutionContext(
        run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='operator', scopes=frozenset({'tools:execute'}),
                                     allowed_tool_ids=frozenset(tools)),
        limits=limits or ExecutionLimits(), assistant=config, model_definition=model,
        model_input=ModelInput(model='test', system_prompt='Helpful',
                               messages=(Message(role='user', content='Count abc'),)))


class MockProvider:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.requests = 0

    async def stream(self, request):
        self.requests += 1
        for chunk in self.scripts.pop(0):
            yield chunk


def collect(agent, ctx):
    async def run():
        return [event async for event in agent.run(ctx)]
    return asyncio.run(run())


def tool_agent(provider, tools, capabilities=('chat', 'streaming', 'tool_calling')):
    return ToolCallingAgent(provider, model_definition=ModelDefinition(id='test', capabilities=set(capabilities)),
                            tool_executor=ToolExecutor(tools), tool_catalog=tools.catalog)


def text_agent(provider, capabilities=('chat', 'streaming')):
    return BasicAgent(provider, model_definition=ModelDefinition(id='test', capabilities=set(capabilities)))


def test_usage_unknown_is_distinct_from_zero_and_cost_needs_rates():
    usage = UsageAccumulator()
    assert usage.value() == {} and usage.budget_tokens() == 0
    assert usage.cost_usd(1, 2) is None
    usage.record_usage({'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150})
    assert usage.value() == {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
    assert usage.cost_usd(1, 2) == 0.0002
    assert usage.cost_usd(None, 2) is None

    zero = UsageAccumulator()
    zero.record_usage({'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
    assert zero.value() == {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    assert zero.budget_tokens() == 0

    partial = UsageAccumulator()
    partial.record_usage({'total_tokens': 5})
    partial.record_text('x' * 40)
    assert partial.value() == {'total_tokens': 5}
    assert partial.budget_tokens() == 5

    missing_total = UsageAccumulator()
    missing_total.record_usage({'prompt_tokens': 5})
    missing_total.record_text('x' * 40)
    assert missing_total.value() == {'prompt_tokens': 5}
    assert missing_total.budget_tokens() == 10


def test_run_budget_enforces_steps_tools_tokens_and_context():
    budget = RunBudget(1, 1, 10, ModelDefinition(id='test', capabilities={'chat'}, context_window=10))
    budget.start_step()
    with pytest.raises(BudgetExceeded) as error:
        budget.start_step()
    assert error.value.code == 'step_limit'
    budget.consume_tool_calls(1)
    with pytest.raises(BudgetExceeded) as error:
        budget.consume_tool_calls(1)
    assert error.value.code == 'tool_call_limit'
    usage = UsageAccumulator()
    usage.record_usage({'total_tokens': 11})
    with pytest.raises(BudgetExceeded) as error:
        budget.check_tokens(usage)
    assert error.value.code == 'token_limit'
    with pytest.raises(BudgetExceeded) as error:
        budget.check_context('x' * 80, output_tokens=5)
    assert error.value.code == 'context_window'


def test_agent_max_steps_and_tool_calls_are_enforced():
    calls = []
    provider = MockProvider([
        [ModelChunk(tool_calls=(ToolCallDelta(index=0, id='call-1', name='test.count',
                                              arguments='{"text":"a"}'),))],
        [ModelChunk(tool_calls=(ToolCallDelta(index=0, id='call-2', name='test.count',
                                              arguments='{"text":"b"}'),))],
    ])
    ctx = context(limits=ExecutionLimits(max_steps=1))
    events = collect(tool_agent(provider, registry(calls)), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'step_limit'
    assert calls == ['a']

    calls = []
    provider = MockProvider([[ModelChunk(tool_calls=(
        ToolCallDelta(index=0, id='call-1', name='test.count', arguments='{"text":"a"}'),
        ToolCallDelta(index=1, id='call-2', name='test.count', arguments='{"text":"b"}'),
    ))]])
    ctx = context(limits=ExecutionLimits(max_tool_calls=1))
    events = collect(tool_agent(provider, registry(calls)), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'tool_call_limit'
    assert calls == []


def test_token_and_context_budgets_stop_generations():
    provider = MockProvider([[ModelChunk(text='hello', usage={'total_tokens': 10})]])
    ctx = context(limits=ExecutionLimits(max_tokens=5))
    events = collect(tool_agent(provider, registry([])), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'token_limit'

    provider = MockProvider([[ModelChunk(text='hello')]])
    ctx = context(context_window=5, max_output_tokens=5)
    events = collect(tool_agent(provider, registry([])), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'context_window'
    assert provider.requests == 0


def test_structured_output_is_validated_when_capability_is_available():
    schema = {'type': 'object', 'additionalProperties': False,
              'required': ['answer'], 'properties': {'answer': {'type': 'string'}}}
    ctx = context(capabilities=('chat', 'streaming', 'structured_output'), tools=(), structured_output=schema)
    events = collect(text_agent(MockProvider([[ModelChunk(text='{"answer":"ok"}')]]),
                                capabilities=('chat', 'streaming', 'structured_output')), ctx)
    assert events[-1].event_type == 'response.completed'
    assert events[-1].payload.text == '{"answer":"ok"}'

    ctx = context(capabilities=('chat', 'streaming', 'structured_output'), tools=(), structured_output=schema)
    events = collect(text_agent(MockProvider([[ModelChunk(text='{"answer":1}')]]),
                                capabilities=('chat', 'streaming', 'structured_output')), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'directive_failed'

    ctx = context(capabilities=('chat', 'streaming'), tools=(), structured_output=schema)
    with pytest.raises(ValueError, match='unsupported_capability'):
        text_agent(MockProvider([[ModelChunk(text='{}')]])).run(ctx)


def test_provider_is_not_retried_after_a_delta():
    class FailingProvider:
        def __init__(self):
            self.calls = 0

        async def stream(self, request):
            self.calls += 1
            yield ModelChunk(text='partial')
            raise ProviderError('stream_failed')

    provider = FailingProvider()
    events = collect(text_agent(provider), context(tools=()))
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'provider_error'
    assert provider.calls == 1


def test_failed_tool_step_stops_without_retry():
    def failing_registry(calls):
        async def fail(params):
            calls.append(params.text)
            raise RuntimeError('boom')
        tools = ToolRegistry()
        tools.register(definition(), input_model=Input, output_model=Output, handler=fail)
        return tools

    calls = []
    provider = MockProvider([
        [ModelChunk(tool_calls=(ToolCallDelta(index=0, id='call-1', name='test.count',
                                              arguments='{"text":"a"}'),))],
        [ModelChunk(tool_calls=(ToolCallDelta(index=0, id='call-2', name='test.count',
                                              arguments='{"text":"b"}'),))],
    ])
    ctx = context(limits=ExecutionLimits(max_tool_calls=1))
    events = collect(tool_agent(provider, failing_registry(calls)), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'tool_failed'
    assert calls == ['a'] and provider.requests == 1


def test_duration_budget_stops_a_slow_provider():
    class SlowProvider:
        async def stream(self, request):
            await asyncio.sleep(0.05)
            yield ModelChunk(text='late')

    ctx = context(limits=ExecutionLimits(duration_seconds=0.005), tools=())
    events = collect(text_agent(SlowProvider()), ctx)
    assert events[-1].event_type == 'agent.failed' and events[-1].payload.code == 'execution_timeout'


def test_invalid_structured_output_schema_is_rejected_at_configuration_time():
    with pytest.raises(ValueError, match='invalid_structured_output_schema'):
        AssistantConfig(id=uuid4(), version=1, name='Test', model='test', system_prompt='Helpful',
                        structured_output={'type': 'not-a-json-schema-type'})
