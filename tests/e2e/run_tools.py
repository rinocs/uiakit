"""Trusted SDK invocation inside the runtime container; no public execute route."""
import asyncio
from uuid import uuid4

from uai_core import ExecutionContext, ExecutionAuthority, ExecutionLimits, ModelInput, Message
from uai_core.tools import ToolExecutionError
from uai_e2e_runtime import from_env


async def verify():
    app = from_env()
    executor = app.state.tool_executor
    context = ExecutionContext(run_id=uuid4(), correlation_id=uuid4(), limits=ExecutionLimits(),
                               authority=ExecutionAuthority(principal_id='e2e-host', scopes={'tools:execute'},
                                                            allowed_tool_ids={'builtin.text_stats'}),
                               model_input=ModelInput(model='test',system_prompt='Helpful',
                                                      messages=(Message(role='user',content='Test'),)))
    result = await executor.execute(context,'builtin.text_stats',{'text':'hello world\nnext'})
    assert result == {'characters':16,'words':3,'lines':2}
    denied = context.model_copy(update={'authority':ExecutionAuthority(principal_id='e2e-host',scopes={'tools:execute'})})
    try:
        await executor.execute(denied,'builtin.text_stats',{'text':'safe'})
    except ToolExecutionError as error:
        assert error.code == 'forbidden'
    else:
        raise AssertionError('tool grant bypassed')
    try:
        await executor.execute(context,'builtin.text_stats',{'text':'safe','authority':{'scopes':['*']}})
    except ToolExecutionError as error:
        assert error.code == 'invalid_input'
    else:
        raise AssertionError('invalid input accepted')


asyncio.run(verify())
print('E2E runtime-owned built-in executor, grant and schema enforcement: passed')
