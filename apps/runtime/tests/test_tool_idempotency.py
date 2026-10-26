import asyncio
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from uai_core.configuration import AssistantConfig
from uai_core.context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from uai_core.models import Message, ModelInput
from uai_core.tools import ToolDefinition, ToolExecutionError
from uai_runtime.tool_executor import (DurableExecutionError, DurableToolRunner, ToolExecution,
                                       ToolExecutionRequest, build_execution_request)
from uai_runtime.approvals import arguments_digest, policy_snapshot


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    q: str


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ok: bool


def tool(risk='read_only'):
    return ToolDefinition(id='test.tool', name='Tool', description='', version='1.0.0',
                          input_schema=Input.model_json_schema(), output_schema=Output.model_json_schema(),
                          permissions={'tools:execute'}, risk_level=risk)


def context():
    base = ExecutionContext(
        run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='user-1', scopes=frozenset({'tools:execute'}),
                                     allowed_tool_ids=frozenset({'test.tool'})),
        limits=ExecutionLimits(),
        model_input=ModelInput(model='test', system_prompt='Helpful',
                               messages=(Message(role='user', content='Hi'),)))
    config = AssistantConfig(id=uuid4(), version=1, name='Test', model='test', system_prompt='Helpful')
    return base.model_copy(update={'assistant': config})


def execution(status='reserved', attempt=1, *, result=None, error=None, request=None):
    request = request or build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    return ToolExecution(id=uuid4(), run_id=request.run_id, tool_id=request.tool_id,
                         tool_version=request.tool_version, arguments_digest=request.arguments_digest,
                         approval_id=request.approval_id, risk_level=request.risk_level,
                         idempotency_key=request.idempotency_key, status=status, attempt=attempt,
                         max_attempts=request.max_attempts, result=result, error_code=error)


class FakeJournal:
    def __init__(self, reserves=None):
        self.reserves = list(reserves or [execution()])
        self.calls = []
        self.completed = []
        self.failed = []
        self.unknowns = []

    async def reserve(self, request):
        self.calls.append(('reserve', request.idempotency_key))
        return self.reserves.pop(0)

    async def start(self, execution_id):
        self.calls.append(('start', execution_id))
        return ToolExecution(id=execution_id, run_id=uuid4(), tool_id='test.tool', tool_version='1.0.0',
                             arguments_digest='a' * 64, risk_level='read_only', idempotency_key='k',
                             status='running', attempt=1, max_attempts=2)

    async def complete(self, execution_id, result):
        self.calls.append(('complete', execution_id))
        self.completed.append(result)
        return execution(status='completed', result=result)

    async def fail(self, execution_id, code):
        self.calls.append(('fail', code))
        self.failed.append(code)
        return execution(status='failed', error=code)

    async def unknown(self, execution_id, code):
        self.calls.append(('unknown', code))
        self.unknowns.append(code)
        return execution(status='unknown', error=code)


def test_execution_request_is_stable_and_bounds_attempts():
    ctx = context()
    first = build_execution_request(ctx, tool(), {'q': 'x'}, tool_call_id='call-1')
    second = build_execution_request(ctx, tool(), {'q': 'x'}, tool_call_id='call-1')
    assert first.idempotency_key == second.idempotency_key
    assert first.arguments_digest == arguments_digest({'q': 'x'})
    assert first.max_attempts == 2 and first.approval_id is None
    assert build_execution_request(ctx, tool(), {'q': 'y'}, tool_call_id='call-1').idempotency_key != first.idempotency_key
    with pytest.raises(ValueError):
        build_execution_request(ctx, tool('write'), {'q': 'x'}, tool_call_id='call-1')
    write = build_execution_request(ctx, tool('write'), {'q': 'x'}, tool_call_id='call-1',
                                    approval_id=uuid4())
    assert write.max_attempts == 1 and write.approval_id is not None


def test_read_only_timeout_retries_and_then_completes():
    request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    journal = FakeJournal([execution(attempt=1), execution(attempt=2)])
    attempts = []

    async def invoke():
        attempts.append(True)
        if len(attempts) == 1:
            raise TimeoutError()
        return {'ok': True}

    result = asyncio.run(DurableToolRunner(journal).run(request, invoke))
    assert result == {'ok': True}
    assert len(attempts) == 2
    assert journal.failed == ['tool_timeout']
    assert journal.completed == [{'ok': True}]


def test_mutating_timeout_becomes_unknown_and_is_never_retried():
    request = build_execution_request(context(), tool('write'), {'q': 'x'}, tool_call_id='call-1',
                                      approval_id=uuid4())
    journal = FakeJournal([execution(attempt=1, request=request)])
    attempts = []

    async def invoke():
        attempts.append(True)
        raise TimeoutError()

    with pytest.raises(DurableExecutionError) as error:
        asyncio.run(DurableToolRunner(journal).run(request, invoke))
    assert error.value.code == 'tool_timeout'
    assert len(attempts) == 1
    assert journal.unknowns == ['tool_timeout']
    assert journal.failed == []


def test_completed_replay_does_not_invoke_the_effect_again():
    request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    journal = FakeJournal([execution(status='completed', result={'ok': True})])
    invoked = []

    async def invoke():
        invoked.append(True)
        return {'ok': False}

    assert asyncio.run(DurableToolRunner(journal).run(request, invoke)) == {'ok': True}
    assert invoked == []
    assert journal.calls == [('reserve', request.idempotency_key)]


def test_failed_or_unknown_status_is_not_retried():
    for status, code in [('failed', 'connector_http_error'), ('unknown', 'effect_unknown')]:
        request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
        journal = FakeJournal([execution(status=status, error=code)])
        with pytest.raises(DurableExecutionError) as error:
            asyncio.run(DurableToolRunner(journal).run(request, lambda: asyncio.sleep(0, result={'ok': True})))
        assert error.value.code == code
        assert journal.calls == [('reserve', request.idempotency_key)]


def test_output_validation_failure_is_failed_for_read_only_and_unknown_for_mutating():
    read_request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    journal = FakeJournal([execution(request=read_request)])

    async def invalid():
        raise ToolExecutionError('invalid_output')

    with pytest.raises(DurableExecutionError) as error:
        asyncio.run(DurableToolRunner(journal).run(read_request, invalid))
    assert error.value.code == 'invalid_output'
    assert journal.failed == ['invalid_output'] and journal.unknowns == []

    write_request = build_execution_request(context(), tool('write'), {'q': 'x'}, tool_call_id='call-2',
                                            approval_id=uuid4())
    journal = FakeJournal([execution(request=write_request)])
    with pytest.raises(DurableExecutionError):
        asyncio.run(DurableToolRunner(journal).run(write_request, invalid))
    assert journal.unknowns == ['invalid_output'] and journal.failed == []


def test_request_validation_rejects_unsafe_keys_and_missing_approval():
    with pytest.raises(ValueError):
        ToolExecutionRequest(run_id=uuid4(), tool_id='test.tool', tool_version='1.0.0',
                             arguments_digest='a' * 64, risk_level='read_only',
                             idempotency_key='', max_attempts=2)
    with pytest.raises(ValueError):
        build_execution_request(context(), tool('write'), {'q': 'x'}, tool_call_id='call-1')


def test_gateway_journal_uses_internal_contract_and_maps_conflict():
    import httpx
    from uai_runtime.tool_executor import ExecutionConflict, GatewayExecutionJournal

    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get('Authorization')))
        return httpx.Response(200, json={'id': str(uuid4()), 'status': 'reserved', 'attempt': 1})

    request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    journal = GatewayExecutionJournal('http://gateway', 'internal-secret',
                                      transport=httpx.MockTransport(handler))
    execution = asyncio.run(journal.reserve(request))
    assert execution.status == 'reserved'
    assert seen == [('POST', '/internal/v1/tool-executions/reserve', 'Bearer internal-secret')]

    conflict = GatewayExecutionJournal(
        'http://gateway', 'internal-secret',
        transport=httpx.MockTransport(lambda request: httpx.Response(409, json={'error': 'conflict'})))
    with pytest.raises(ExecutionConflict):
        asyncio.run(conflict.reserve(request))
