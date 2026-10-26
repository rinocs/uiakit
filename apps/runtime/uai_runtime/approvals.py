"""Immutable, canonical approval bindings shared by the runtime and gateway."""
import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from uai_core.context import ExecutionContext
from uai_core.tools import ToolDefinition, ToolID

ApprovalStatus = Literal['pending', 'approved', 'rejected', 'expired', 'invalidated', 'consumed']
Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
MAX_POLICY_BYTES = 8192
MAX_TTL_SECONDS = 86400


class ApprovalError(Exception):
    code = 'approval_error'

    def __init__(self, code: str | None = None):
        self.code = code or self.code
        super().__init__(self.code)


class ApprovalExpired(ApprovalError):
    code = 'approval_expired'


class ApprovalAlreadyDecided(ApprovalError):
    code = 'approval_already_decided'


class ApprovalBindingMismatch(ApprovalError):
    code = 'approval_binding_mismatch'


class ApprovalNotApproved(ApprovalError):
    code = 'approval_not_approved'


class ApprovalConsumed(ApprovalError):
    code = 'approval_consumed'


def _jsonable(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode='json')
    return value


def canonical_json(value) -> bytes:
    try:
        return json.dumps(_jsonable(value), sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError):
        raise ValueError('invalid_approval_json') from None


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def arguments_digest(arguments) -> str:
    return _digest(arguments)


def policy_digest(policy) -> str:
    return _digest(policy)


def policy_snapshot(context: ExecutionContext, tool: ToolDefinition, *,
                    allowed_connectors: Iterable[str] | None = None) -> dict[str, JsonValue]:
    """Everything that can invalidate an approval, without prompts or tool arguments."""
    assistant = context.assistant
    return {
        'assistant': None if assistant is None else {
            'id': str(assistant.id),
            'version': assistant.version,
            'tools': sorted(assistant.tools),
            'require_tool_approval': assistant.policy.require_tool_approval,
        },
        'principal': {
            'id': context.authority.principal_id,
            'scopes': sorted(context.authority.scopes),
            'allowed_tool_ids': sorted(context.authority.allowed_tool_ids),
        },
        'tool': {
            'id': tool.id,
            'version': tool.version,
            'permissions': sorted(tool.permissions),
            'risk_level': tool.risk_level,
            'executor': tool.executor,
        },
        'connector_allowlist': None if allowed_connectors is None else sorted(allowed_connectors),
    }


def _now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('approval_timeout_naive')
    return value.astimezone(timezone.utc)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('approval_time_naive')
    return value.astimezone(timezone.utc)


class Approval(BaseModel):
    """A decision is bound to the exact run, tool version, arguments and policy."""

    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    id: UUID
    run_id: UUID
    tool_id: ToolID
    tool_version: str = Field(pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$')
    arguments_digest: Sha256
    policy_digest: Sha256
    policy_snapshot: dict[str, JsonValue]
    requested_by: str = Field(min_length=1, max_length=200)
    status: ApprovalStatus = 'pending'
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = Field(default=None, min_length=1, max_length=200)
    consumed_at: datetime | None = None

    @field_validator('created_at', 'expires_at', 'decided_at', 'consumed_at')
    @classmethod
    def normalize_times(cls, value):
        return None if value is None else _utc(value)

    @model_validator(mode='after')
    def validate_binding(self):
        if not self.expires_at > self.created_at or self.expires_at - self.created_at > timedelta(
                seconds=MAX_TTL_SECONDS):
            raise ValueError('invalid_approval_expiry')
        if len(canonical_json(self.policy_snapshot)) > MAX_POLICY_BYTES:
            raise ValueError('approval_policy_too_large')
        if self.policy_digest != policy_digest(self.policy_snapshot):
            raise ValueError('approval_policy_digest_mismatch')
        if self.status in ('pending', 'expired', 'invalidated'):
            if self.decided_at is not None or self.decided_by is not None:
                raise ValueError('invalid_approval_decision_state')
        elif self.decided_at is None or self.decided_by is None:
            raise ValueError('invalid_approval_decision_state')
        if self.status == 'consumed':
            if self.consumed_at is None:
                raise ValueError('invalid_approval_consumption_state')
        elif self.consumed_at is not None:
            raise ValueError('invalid_approval_consumption_state')
        return self

    @classmethod
    def create(cls, *, run_id: UUID, tool: ToolDefinition, arguments, policy: dict[str, JsonValue],
               requested_by: str, ttl_seconds: int = 300, now: datetime | None = None,
               approval_id: UUID | None = None) -> 'Approval':
        current = _now(now)
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 0 < ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError('invalid_approval_ttl')
        encoded = canonical_json(policy)
        if len(encoded) > MAX_POLICY_BYTES:
            raise ValueError('approval_policy_too_large')
        return cls(id=approval_id or uuid4(), run_id=run_id, tool_id=tool.id,
                   tool_version=tool.version, arguments_digest=arguments_digest(arguments),
                   policy_digest=hashlib.sha256(encoded).hexdigest(), policy_snapshot=policy,
                   requested_by=requested_by, created_at=current,
                   expires_at=current + timedelta(seconds=ttl_seconds))

    def _replace(self, **updates) -> 'Approval':
        return Approval.model_validate({**self.model_dump(), **updates})

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return _now(now) >= self.expires_at

    def matches(self, *, tool: ToolDefinition, arguments, policy: dict[str, JsonValue]) -> bool:
        return (self.tool_id == tool.id and self.tool_version == tool.version
                and self.arguments_digest == arguments_digest(arguments)
                and self.policy_digest == policy_digest(policy))

    def approve(self, approver: str, *, now: datetime | None = None) -> 'Approval':
        current = _now(now)
        if self.status != 'pending':
            raise ApprovalAlreadyDecided()
        if current >= self.expires_at:
            raise ApprovalExpired()
        return self._replace(status='approved', decided_at=current, decided_by=approver)

    def reject(self, approver: str, *, now: datetime | None = None) -> 'Approval':
        current = _now(now)
        if self.status != 'pending':
            raise ApprovalAlreadyDecided()
        if current >= self.expires_at:
            raise ApprovalExpired()
        return self._replace(status='rejected', decided_at=current, decided_by=approver)

    def invalidate(self) -> 'Approval':
        if self.status not in ('pending', 'approved'):
            raise ApprovalAlreadyDecided()
        return self._replace(status='invalidated', decided_at=None, decided_by=None, consumed_at=None)

    def consume(self, *, tool: ToolDefinition, arguments, policy: dict[str, JsonValue],
                now: datetime | None = None) -> 'Approval':
        current = _now(now)
        if self.status == 'consumed':
            raise ApprovalConsumed()
        if self.status != 'approved':
            raise ApprovalNotApproved()
        if current >= self.expires_at:
            raise ApprovalExpired()
        if not self.matches(tool=tool, arguments=arguments, policy=policy):
            raise ApprovalBindingMismatch()
        return self._replace(status='consumed', consumed_at=current)
