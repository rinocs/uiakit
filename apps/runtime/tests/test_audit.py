import asyncio
import logging
from uuid import uuid4

import pytest

from uai_runtime.audit import AuditEvent, AuditLog, redact_details
from uai_runtime.tool_executor import DurableExecutionError, DurableToolRunner, build_execution_request
from test_tool_idempotency import FakeJournal, context, tool


def test_redaction_is_recursive_and_covers_auth_material():
    value = redact_details({
        'authorization': 'Bearer secret', 'nested': {'api_key': 'k', 'safe': 1},
        'items': [{'password': 'p'}, {'tool': 'read'}], 'headers': {'x': 'y'},
    })
    text = str(value)
    assert 'Bearer' not in text and "'k'" not in text and "'p'" not in text
    assert value['nested']['safe'] == 1 and value['items'][1]['tool'] == 'read'
    assert value['nested']['api_key'] == '[redacted]'


def test_audit_failure_blocks_the_effect_before_start():
    effects = []

    def broken(_payload):
        raise RuntimeError('audit unavailable')

    request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    runner = DurableToolRunner(FakeJournal(), AuditLog(broken))

    async def invoke():
        effects.append('ran')
        return {'ok': True}

    with pytest.raises(DurableExecutionError) as error:
        asyncio.run(runner.run(request, invoke))
    assert error.value.code == 'audit_unavailable'
    assert effects == []


def test_audit_event_contains_binding_without_arguments_or_results():
    seen = []
    request = build_execution_request(context(), tool(), {'q': 'x'}, tool_call_id='call-1')
    runner = DurableToolRunner(FakeJournal(), AuditLog(seen.append))

    result = asyncio.run(runner.run(request, lambda: asyncio.sleep(0, result={'ok': True})))
    assert result == {'ok': True}
    assert seen and seen[0]['action'] == 'tool_execution.authorized'
    assert seen[0]['run_id'] == str(request.run_id)
    assert seen[0]['digest'] == request.arguments_digest
    assert 'q' not in seen[0]['details'] and 'result' not in seen[0]['details']


def test_default_runtime_audit_log_never_prints_authorization(caplog):
    event = AuditEvent(
        action='tool_execution.authorized', actor_id='user-1', target_id=uuid4(),
        run_id=uuid4(), correlation_id=uuid4(), outcome='authorized',
        details={'authorization': 'Bearer secret', 'tool_id': 'read'})
    with caplog.at_level(logging.INFO, logger='uai.audit'):
        AuditLog().record(event)
    assert 'Bearer secret' not in caplog.text
    assert '[redacted]' in caplog.text and 'read' in caplog.text
