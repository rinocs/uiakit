import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from uai_core.tools import ToolDefinition, ToolExecutionError
from uai_core.context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from uai_core.models import Message, ModelInput
from uai_runtime.tool_registry import ToolRegistry, ToolExecutor, default_tool_registry


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(max_length=32000)


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    characters: int = Field(ge=0)


def definition(**updates):
    values = dict(id='test.count', name='Count', description='Counts characters', version='1.0.0',
                  permissions={'tools:execute'}, risk_level='read_only', timeout=.1,
                  retry_policy='never', executor='builtin', input_schema=Input.model_json_schema(),
                  output_schema=Output.model_json_schema())
    values.update(updates)
    return ToolDefinition(**values)


def context(*, scopes=frozenset({'tools:execute'}), grants=frozenset({'test.count'}), limits=None):
    return ExecutionContext(run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='operator', scopes=scopes, allowed_tool_ids=grants),
        limits=limits or ExecutionLimits(), model_input=ModelInput(model='test',system_prompt='Helpful',
                                                                  messages=(Message(role='user',content='Hi'),)))


def register(handler, **updates):
    registry = ToolRegistry()
    registry.register(definition(**updates), input_model=Input, output_model=Output, handler=handler)
    return registry


def test_registration_validates_schema_identity_and_detaches_metadata():
    async def count(params):
        return Output(characters=len(params.text))
    descriptor = definition()
    registry = ToolRegistry()
    registry.register(descriptor, input_model=Input, output_model=Output, handler=count)
    descriptor.input_schema.clear()
    catalog = registry.catalog()
    assert catalog[0].input_schema['type'] == 'object'
    catalog[0].input_schema.clear()
    assert registry.catalog()[0].input_schema['type'] == 'object'
    with pytest.raises(ValueError):
        registry.register(definition(), input_model=Input, output_model=Output, handler=count)
    with pytest.raises(ValueError):
        register(count, input_schema={'type':'string'})
    with pytest.raises(ValidationError):
        definition(executor='python_module_from_user')
    with pytest.raises(ValidationError):
        definition(retry_policy='always')


@pytest.mark.parametrize('scopes,grants', [([],[]), (['tools:execute'],[]), ([],['test.count']), (['*'],['test.count'])])
def test_authorization_is_explicit_before_handler(scopes, grants):
    calls = []
    async def count(params):
        calls.append(params)
        return Output(characters=1)
    executor = ToolExecutor(register(count))
    with pytest.raises(ToolExecutionError) as error:
        asyncio.run(executor.execute(context(scopes=frozenset(scopes), grants=frozenset(grants)), 'test.count', {'text':'secret'}))
    assert error.value.code == 'forbidden'
    assert calls == []


def test_declared_permissions_and_assistant_selection_cannot_be_bypassed():
    from test_capabilities import assistant_config
    from uai_core.configuration import AssistantConfig
    async def count(params):
        pytest.fail('not authorized')
    executor = ToolExecutor(register(count, permissions={'tools:execute','files:read'}))
    with pytest.raises(ToolExecutionError, match='forbidden'):
        asyncio.run(executor.execute(context(), 'test.count', {'text':'secret'}))
    ctx = context().model_copy(update={'assistant': AssistantConfig(**assistant_config())})
    executor = ToolExecutor(register(count))
    with pytest.raises(ToolExecutionError, match='forbidden'):
        asyncio.run(executor.execute(ctx, 'test.count', {'text':'secret'}))


@pytest.mark.parametrize('arguments', [{'text':1}, {'text':'safe','authority':{'scopes':['*']}}, {'text':'x'*32001}, {'text':float('nan')}, {1:'not a JSON key'}])
def test_invalid_arguments_never_reach_handler(arguments):
    calls = []
    async def count(params):
        calls.append(params)
        return Output(characters=1)
    with pytest.raises(ToolExecutionError) as error:
        asyncio.run(ToolExecutor(register(count)).execute(context(),'test.count', arguments))
    assert error.value.code == 'invalid_input'
    assert not calls


def test_valid_execution_emits_real_lifecycle_without_leaking_arguments_or_output(caplog):
    from uai_runtime.hooks import HookRegistry, HookSubscriber
    observations = []
    async def observe(event):
        observations.append(event)
    hooks = HookRegistry()
    hooks.register(HookSubscriber(name='test.observe',callback=observe))
    async def count(params):
        return Output(characters=len(params.text))
    caplog.set_level('INFO')
    ctx = context()
    result = asyncio.run(ToolExecutor(register(count), hook_registry=hooks).execute(ctx,'test.count',{'text':'private argument'}))
    assert result == {'characters':16}
    assert [e.event_type for e in observations] == ['tool.requested','tool.authorized','tool.started','tool.completed']
    assert all(e.run_id == ctx.run_id and e.correlation_id == ctx.correlation_id for e in observations)
    assert 'private argument' not in caplog.text + ''.join(e.model_dump_json() for e in observations)
    assert str(ctx.run_id) in caplog.text


def test_schema_invalid_output_and_executor_exception_are_normalized_without_retry(caplog):
    for output in [{'characters':-1}, {'characters':True}, Output(characters=1).model_copy(update={'characters':-1}), RuntimeError('private API key')]:
        calls = []
        async def handler(params):
            calls.append(True)
            if isinstance(output,Exception):
                raise output
            return output
        with pytest.raises(ToolExecutionError) as error:
            asyncio.run(ToolExecutor(register(handler)).execute(context(),'test.count',{'text':'private input'}))
        assert error.value.code == ('executor_error' if isinstance(output,Exception) else 'invalid_output')
        assert calls == [True]
        assert 'private API key' not in str(error.value) + caplog.text


def test_timeout_cancellation_and_limits_are_enforced():
    closed = []
    async def slow(params):
        try:
            await asyncio.sleep(10)
        finally:
            closed.append(True)
    with pytest.raises(ToolExecutionError, match='tool_timeout'):
        asyncio.run(ToolExecutor(register(slow, timeout=.001)).execute(context(),'test.count',{'text':'safe'}))
    assert closed == [True]
    async def count(params):
        return Output(characters=1)
    ctx = context(limits=ExecutionLimits(max_output_chars=2))
    with pytest.raises(ToolExecutionError, match='output_limit'):
        asyncio.run(ToolExecutor(register(count)).execute(ctx,'test.count',{'text':'safe'}))


def test_non_readonly_tools_fail_before_execution_even_with_grants():
    async def write(params):
        pytest.fail('approval bypassed')
    with pytest.raises(ToolExecutionError, match='approval_required'):
        asyncio.run(ToolExecutor(register(write,risk_level='write')).execute(context(),'test.count',{'text':'safe'}))


def test_builtin_stats_treats_hostile_text_as_data():
    registry = default_tool_registry()
    descriptor = registry.catalog()[0]
    assert descriptor.id == 'builtin.text_stats' and descriptor.executor == 'builtin'
    hostile = '__import__("os").system("touch /tmp/tool-must-not-execute")\nhello'
    ctx = context(grants={'builtin.text_stats'})
    result = asyncio.run(ToolExecutor(registry).execute(ctx,'builtin.text_stats',{'text':hostile}))
    assert result == {'characters':len(hostile),'words':len(hostile.split()),'lines':2}


def test_catalog_endpoint_is_authenticated_metadata_only():
    from test_capabilities import send, Provider
    from uai_runtime.app import create_app
    app = create_app('internal-secret',Provider())
    assert send(app,'/internal/v1/tools',authorized=False).status_code == 401
    response = send(app,'/internal/v1/tools')
    assert response.status_code == 200
    tool = response.json()[0]
    assert tool['id'] == 'builtin.text_stats'
    assert not {'handler','module','api_key','base_url','principal_id'} & tool.keys()
    assert set(tool) == set(ToolDefinition.model_fields)


def test_limits_apply_after_model_normalization():
    from pydantic import field_validator
    class Expanding(BaseModel):
        model_config = ConfigDict(extra='forbid', strict=True)
        text: str

        @field_validator('text')
        @classmethod
        def expand(cls, value):
            return value * 100

    async def result(params):
        return {'text':'x'}
    registry = ToolRegistry()
    metadata = definition(output_schema=Expanding.model_json_schema())
    registry.register(metadata,input_model=Input,output_model=Expanding,handler=result)
    ctx = context(limits=ExecutionLimits(max_output_chars=20))
    with pytest.raises(ToolExecutionError, match='output_limit'):
        asyncio.run(ToolExecutor(registry).execute(ctx,'test.count',{'text':'safe'}))
    async def never(params):
        pytest.fail('expanded input exceeded the budget')
    registry = ToolRegistry()
    registry.register(definition(input_schema=Expanding.model_json_schema()),
                      input_model=Expanding, output_model=Output, handler=never)
    ctx = context(limits=ExecutionLimits(max_input_chars=20))
    with pytest.raises(ToolExecutionError, match='input_limit'):
        asyncio.run(ToolExecutor(registry).execute(ctx,'test.count',{'text':'x'}))


def test_caller_cancellation_propagates_and_is_audited(caplog):
    from uai_runtime.hooks import HookRegistry, HookSubscriber
    reached = asyncio.Event()
    closed = []
    observed = []
    async def record(event):
        observed.append(event)
    async def wait(params):
        try:
            reached.set()
            await asyncio.Event().wait()
        finally:
            closed.append(True)
    hooks = HookRegistry()
    hooks.register(HookSubscriber(name='capture',callback=record))
    executor = ToolExecutor(register(wait,timeout=10), hook_registry=hooks)
    async def run():
        task = asyncio.create_task(executor.execute(context(),'test.count',{'text':'private'}))
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed == [True]
    asyncio.run(run())
    assert observed[-1].event_type == 'tool.failed'
    assert observed[-1].payload.code == 'cancelled'
    assert 'cancelled' in caplog.text and 'private' not in caplog.text


def test_factory_catalog_and_executor_share_the_same_registry():
    from test_capabilities import send, Provider
    from uai_runtime.app import create_app
    async def count(params):
        return Output(characters=len(params.text))
    registry = register(count)
    app = create_app('internal-secret',Provider(),tool_registry=registry)
    assert send(app,'/internal/v1/tools').json()[0]['id'] == 'test.count'
    result = asyncio.run(app.state.tool_executor.execute(context(),'test.count',{'text':'four'}))
    assert result == {'characters':4}
