import asyncio
import json

import pytest
from pydantic import BaseModel, ConfigDict, Field

from uai_core.capabilities import ModelDefinition
from uai_core.configuration import AssistantConfig
from uai_core.context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from uai_core.models import Message, ModelInput
from uai_core.providers import ModelChunk, ToolCallDelta
from uai_core.tools import ToolDefinition
from uai_runtime.tool_loop import ToolCallingAgent
from uai_runtime.tool_registry import ToolExecutor, ToolRegistry


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(max_length=1000)


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    characters: int = Field(ge=0)


def definition():
    return ToolDefinition(id='test.count', name='Count', description='Counts characters', version='1.0.0',
                          input_schema=Input.model_json_schema(), output_schema=Output.model_json_schema(),
                          permissions={'tools:execute'}, risk_level='read_only')


def registry(calls):
    async def count(params):
        calls.append(params.text)
        return Output(characters=len(params.text))
    tools = ToolRegistry()
    tools.register(definition(), input_model=Input, output_model=Output, handler=count)
    return tools


def context(*, tools=('test.count',), capabilities=('chat', 'streaming', 'tool_calling')):
    config = AssistantConfig(id=__import__('uuid').uuid4(), version=1, name='Test', model='test',
                             system_prompt='Helpful', tools=tools)
    return ExecutionContext(
        run_id=__import__('uuid').uuid4(), correlation_id=__import__('uuid').uuid4(),
        authority=ExecutionAuthority(principal_id='operator', scopes=frozenset({'tools:execute'}),
                                     allowed_tool_ids=frozenset(tools)),
        limits=ExecutionLimits(), assistant=config,
        model_definition=ModelDefinition(id='test', capabilities=set(capabilities)),
        model_input=ModelInput(model='test', system_prompt='Helpful',
                               messages=(Message(role='user', content='Count abc'),)))


class MockProvider:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        for chunk in self.scripts.pop(0):
            yield chunk


def collect(agent, ctx):
    async def run():
        return [event async for event in agent.run(ctx)]
    return asyncio.run(run())


def agent(provider, tools):
    return ToolCallingAgent(provider, model_definition=ModelDefinition(id='test', capabilities={
        'chat', 'streaming', 'tool_calling'}), tool_executor=ToolExecutor(tools),
        tool_catalog=tools.catalog)


def test_direct_response_without_tool_calls():
    calls = []
    provider = MockProvider([[ModelChunk(text='hello')]])
    events = collect(agent(provider, registry(calls)), context())
    assert [item.event_type for item in events] == ['agent.started', 'response.delta', 'response.completed']
    assert events[-1].payload.text == 'hello'
    assert calls == []


def test_tool_call_result_and_second_generation():
    calls = []
    provider = MockProvider([
        [ModelChunk(tool_calls=(ToolCallDelta(index=0, id='call-1', name='test.count',
                                              arguments='{"text":"abc"}'),))],
        [ModelChunk(text='done')],
    ])
    events = collect(agent(provider, registry(calls)), context())
    assert events[-1].event_type == 'response.completed'
    assert events[-1].payload.text == 'done'
    assert calls == ['abc']
    assert len(provider.requests) == 2
    second = provider.requests[1]
    assert second.tools and second.tools[0]['function']['name'] == 'test.count'
    assistant = second.provider_messages[-2]
    assert assistant['role'] == 'assistant' and assistant['tool_calls'][0]['id'] == 'call-1'
    tool = second.provider_messages[-1]
    assert tool['role'] == 'tool' and tool['tool_call_id'] == 'call-1'
    assert json.loads(tool['content']) == {'characters': 3}


def test_partial_or_malformed_tool_json_is_never_executed():
    calls = []
    for arguments in ['{"text":', 'not-json', '{"text": NaN}', '["text"]']:
        provider = MockProvider([[ModelChunk(tool_calls=(ToolCallDelta(
            index=0, id='call-1', name='test.count', arguments=arguments),))]])
        events = collect(agent(provider, registry(calls)), context())
        assert events[-1].event_type == 'agent.failed'
        assert events[-1].payload.code == 'tool_call_invalid'
    assert calls == []


def test_unknown_or_unselected_tool_is_not_executed():
    calls = []
    provider = MockProvider([[ModelChunk(tool_calls=(ToolCallDelta(
        index=0, id='call-1', name='admin.delete', arguments='{}'),))]])
    events = collect(agent(provider, registry(calls)), context())
    assert events[-1].event_type == 'agent.failed'
    assert events[-1].payload.code == 'tool_not_authorized'
    assert calls == []


def test_tool_result_is_untrusted_data_not_a_system_instruction():
    calls = []
    provider = MockProvider([
        [ModelChunk(tool_calls=(ToolCallDelta(index=0, id='call-1', name='test.count',
                                              arguments='{"text":"abc"}'),))],
        [ModelChunk(text='safe')],
    ])
    ctx = context()
    events = collect(agent(provider, registry(calls)), ctx)
    assert events[-1].payload.text == 'safe'
    tool = provider.requests[1].provider_messages[-1]
    assert tool['role'] == 'tool'
    assert all(message.get('role') != 'system' for message in provider.requests[1].provider_messages[1:])


def test_tool_calling_capability_is_required():
    calls = []
    provider = MockProvider([[ModelChunk(text='hello')]])
    ctx = context(capabilities=('chat', 'streaming'))
    without_tools = ToolCallingAgent(provider, model_definition=ModelDefinition(
        id='test', capabilities={'chat', 'streaming'}),
        tool_executor=ToolExecutor(registry(calls)), tool_catalog=registry(calls).catalog)
    with pytest.raises(ValueError, match='unsupported_capability'):
        without_tools.run(ctx)


def test_tool_executor_failure_fails_closed():
    async def broken(params):
        raise RuntimeError('private')
    tools = ToolRegistry()
    tools.register(definition(), input_model=Input, output_model=Output, handler=broken)
    provider = MockProvider([[ModelChunk(tool_calls=(ToolCallDelta(
        index=0, id='call-1', name='test.count', arguments='{"text":"abc"}'),))]])
    events = collect(agent(provider, tools), context())
    assert events[-1].event_type == 'agent.failed'
    assert events[-1].payload.code == 'tool_failed'
