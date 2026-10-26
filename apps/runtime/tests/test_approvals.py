from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from uai_core.configuration import AssistantConfig
from uai_core.context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from uai_core.models import Message, ModelInput
from uai_core.tools import ToolDefinition
from uai_runtime.approvals import (Approval, ApprovalAlreadyDecided, ApprovalBindingMismatch,
                                   ApprovalConsumed, ApprovalExpired, ApprovalNotApproved,
                                   arguments_digest, policy_snapshot)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    q: str


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ok: bool


def tool(version='1.0.0'):
    return ToolDefinition(id='test.write', name='Write', description='Writes', version=version,
                          input_schema=Input.model_json_schema(), output_schema=Output.model_json_schema(),
                          permissions={'tools:execute', 'files:write'}, risk_level='write')


def context(*, version=1, scopes=('tools:execute', 'files:write'), grants=('test.write',), assistant=True):
    snapshot = None
    if assistant:
        config = AssistantConfig(id=uuid4(), version=version, name='Test', model='test',
                                 system_prompt='Helpful')
        snapshot = config.model_copy(update={'tools': ('test.write',)})
    base = ExecutionContext(
        run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='user-1', scopes=frozenset(scopes),
                                     allowed_tool_ids=frozenset(grants)),
        limits=ExecutionLimits(),
        model_input=ModelInput(model='test', system_prompt='Helpful',
                               messages=(Message(role='user', content='Hi'),)))
    return base.model_copy(update={'assistant': snapshot}) if snapshot is not None else base


def approval(*, ctx=None, definition=None, arguments=None, ttl=300, now=None):
    ctx = ctx or context()
    definition = definition or tool()
    arguments = arguments if arguments is not None else {'q': 'hello', 'path': '/tmp/x'}
    return Approval.create(run_id=ctx.run_id, tool=definition, arguments=arguments,
                           policy=policy_snapshot(ctx, definition), requested_by='user-2',
                           ttl_seconds=ttl, now=now)


def test_canonical_arguments_digest_is_stable_and_finite():
    assert arguments_digest({'b': 1, 'a': [2, 3]}) == arguments_digest({'a': [2, 3], 'b': 1})
    assert arguments_digest({'a': 1}) != arguments_digest({'a': 2})
    with pytest.raises(ValueError):
        arguments_digest({'a': float('nan')})


def test_approval_binds_run_tool_version_arguments_policy_and_expiry():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    ctx = context(version=3)
    definition = tool(version='1.2.3')
    item = approval(ctx=ctx, definition=definition, now=now)
    assert item.status == 'pending' and item.expires_at == now + timedelta(seconds=300)
    assert item.tool_id == 'test.write' and item.tool_version == '1.2.3'
    assert item.arguments_digest == arguments_digest({'q': 'hello', 'path': '/tmp/x'})
    assert item.policy_snapshot['assistant']['version'] == 3
    assert item.policy_snapshot['principal']['scopes'] == ['files:write', 'tools:execute']
    assert item.policy_snapshot['tool']['version'] == '1.2.3'
    assert item.matches(tool=definition, arguments={'q': 'hello', 'path': '/tmp/x'},
                        policy=policy_snapshot(ctx, definition))
    assert not item.matches(tool=tool(version='1.2.4'), arguments={'q': 'hello', 'path': '/tmp/x'},
                            policy=policy_snapshot(ctx, tool(version='1.2.4')))


def test_arguments_policy_and_tool_version_changes_break_the_binding():
    item = approval()
    current = context()
    definition = tool()
    policy = policy_snapshot(current, definition)
    assert not item.matches(tool=definition, arguments={'q': 'changed'}, policy=policy)
    assert not item.matches(tool=definition, arguments={'q': 'hello', 'path': '/tmp/x'},
                            policy=policy_snapshot(context(version=2), definition))
    assert not item.matches(tool=tool(version='2.0.0'), arguments={'q': 'hello', 'path': '/tmp/x'},
                            policy=policy_snapshot(current, tool(version='2.0.0')))
    assert not item.matches(tool=definition, arguments={'q': 'hello', 'path': '/tmp/x'},
                            policy=policy_snapshot(context(scopes=('tools:execute',)), definition))
    assert not item.matches(tool=definition, arguments={'q': 'hello', 'path': '/tmp/x'},
                            policy=policy_snapshot(current, definition,
                                                   allowed_connectors={'example'}))


def test_approval_can_only_be_decided_once_and_expires():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    item = approval(now=now)
    approved = item.approve('approver', now=now + timedelta(seconds=1))
    assert approved.status == 'approved' and approved.decided_by == 'approver'
    with pytest.raises(ApprovalAlreadyDecided):
        approved.approve('approver', now=now + timedelta(seconds=2))
    with pytest.raises(ApprovalAlreadyDecided):
        approved.reject('approver', now=now + timedelta(seconds=2))
    with pytest.raises(ApprovalExpired):
        approval(now=now - timedelta(seconds=301)).approve('approver', now=now)
    with pytest.raises(ApprovalExpired):
        approved.consume(tool=tool(), arguments={'q': 'hello', 'path': '/tmp/x'},
                         policy=policy_snapshot(context(), tool()), now=now + timedelta(seconds=301))


def test_approved_approval_is_single_use_and_rechecks_the_binding():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    definition = tool()
    current = context()
    arguments = {'q': 'hello', 'path': '/tmp/x'}
    policy = policy_snapshot(current, definition)
    item = approval(ctx=current, definition=definition, arguments=arguments, now=now).approve(
        'approver', now=now + timedelta(seconds=1))
    consumed = item.consume(tool=definition, arguments=arguments, policy=policy,
                            now=now + timedelta(seconds=2))
    assert consumed.status == 'consumed' and consumed.consumed_at is not None
    with pytest.raises(ApprovalConsumed):
        consumed.consume(tool=definition, arguments=arguments, policy=policy,
                         now=now + timedelta(seconds=3))
    with pytest.raises(ApprovalBindingMismatch):
        item.consume(tool=definition, arguments={'q': 'other', 'path': '/tmp/x'}, policy=policy,
                     now=now + timedelta(seconds=2))
    with pytest.raises(ApprovalBindingMismatch):
        item.consume(tool=tool(version='2.0.0'), arguments=arguments,
                     policy=policy_snapshot(current, tool(version='2.0.0')),
                     now=now + timedelta(seconds=2))
    with pytest.raises(ApprovalNotApproved):
        approval(now=now).consume(tool=definition, arguments=arguments, policy=policy, now=now)


def test_invalidation_blocks_consumption():
    item = approval().approve('approver')
    invalidated = item.invalidate()
    assert invalidated.status == 'invalidated'
    with pytest.raises(ApprovalNotApproved):
        invalidated.consume(tool=tool(), arguments={'q': 'hello', 'path': '/tmp/x'},
                            policy=policy_snapshot(context(), tool()))


def test_ttl_policy_size_and_timezone_are_bounded():
    with pytest.raises(ValueError):
        approval(ttl=0)
    with pytest.raises(ValueError):
        approval(ttl=86401)
    with pytest.raises(ValueError):
        approval(ttl=-1)
    with pytest.raises(ValueError):
        approval(now=datetime(2026, 10, 24, 12, 0))
    with pytest.raises(ValueError):
        Approval.create(run_id=uuid4(), tool=tool(), arguments={'q': 'x'},
                        policy={'padding': 'x' * 9000}, requested_by='user-2')
    with pytest.raises(ValidationError):
        Approval.model_validate({**approval().model_dump(), 'status': 'approved'})
