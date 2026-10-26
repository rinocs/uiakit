"""Durable tool execution: idempotent reservation, bounded retries and unknown effects."""
import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from uai_core.context import ExecutionContext
from uai_core.tools import ToolDefinition, ToolExecutionError, ToolID
from .approvals import Sha256, arguments_digest
from .audit import AuditEvent, AuditLog

ExecutionStatus = Literal['reserved', 'running', 'completed', 'failed', 'unknown']
RETRYABLE_CODES = frozenset({'tool_timeout', 'connector_unavailable'})


class DurableExecutionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ToolExecutionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    run_id: UUID
    tool_id: ToolID
    tool_version: str = Field(pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$')
    arguments_digest: Sha256
    approval_id: UUID | None = None
    risk_level: Literal['read_only', 'write', 'destructive']
    idempotency_key: str = Field(min_length=1, max_length=200)
    max_attempts: int = Field(ge=1, le=3)
    principal_id: str = Field(default='internal', min_length=1, max_length=200)
    correlation_id: UUID | None = None

    @model_validator(mode='after')
    def bound_effects(self):
        if self.risk_level != 'read_only' and (self.approval_id is None or self.max_attempts != 1):
            raise ValueError('approval_and_single_attempt_required')
        return self


class ToolExecution(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: UUID
    status: ExecutionStatus
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=1, ge=1, le=3)
    result: JsonValue | None = None
    error_code: str | None = None


def build_execution_request(context: ExecutionContext, tool: ToolDefinition, arguments,
                            *, tool_call_id: str, approval_id: UUID | None = None,
                            max_read_only_attempts: int = 2) -> ToolExecutionRequest:
    if not tool_call_id or len(tool_call_id) > 200:
        raise ValueError('invalid_tool_call_id')
    if not 1 <= max_read_only_attempts <= 3:
        raise ValueError('invalid_max_attempts')
    digest = arguments_digest(arguments)
    key_material = '\x1f'.join([str(context.run_id), tool_call_id, tool.id, tool.version,
                                digest, str(approval_id) if approval_id is not None else ''])
    key = hashlib.sha256(key_material.encode('utf-8')).hexdigest()
    return ToolExecutionRequest(
        run_id=context.run_id, tool_id=tool.id, tool_version=tool.version,
        arguments_digest=digest, approval_id=approval_id, risk_level=tool.risk_level,
        idempotency_key=key, principal_id=context.authority.principal_id,
        correlation_id=context.correlation_id,
        max_attempts=max_read_only_attempts if tool.risk_level == 'read_only' else 1)


class ExecutionJournal(Protocol):
    async def reserve(self, request: ToolExecutionRequest) -> ToolExecution: ...
    async def start(self, execution_id: UUID) -> ToolExecution: ...
    async def complete(self, execution_id: UUID, result: JsonValue) -> ToolExecution: ...
    async def fail(self, execution_id: UUID, code: str) -> ToolExecution: ...
    async def unknown(self, execution_id: UUID, code: str) -> ToolExecution: ...


class DurableToolRunner:
    def __init__(self, journal: ExecutionJournal, audit: AuditLog | None = None):
        self._journal = journal
        self._audit = audit

    async def run(self, request: ToolExecutionRequest,
                  invoke: Callable[[], Awaitable[JsonValue]]) -> JsonValue:
        while True:
            execution = await self._journal.reserve(request)
            if execution.status == 'completed':
                return execution.result
            if execution.status in ('failed', 'unknown'):
                raise DurableExecutionError(execution.error_code or execution.status)
            if execution.status != 'reserved':
                raise DurableExecutionError('execution_conflict')
            if self._audit is not None:
                try:
                    self._audit.record(AuditEvent(
                        action='tool_execution.authorized', actor_id=request.principal_id,
                        target_id=execution.id, run_id=request.run_id,
                        correlation_id=request.correlation_id or context_correlation(request),
                        digest=request.arguments_digest, outcome='authorized',
                        details={'tool_id': request.tool_id, 'tool_version': request.tool_version,
                                 'risk_level': request.risk_level,
                                 'attempt': execution.attempt,
                                 'max_attempts': request.max_attempts}))
                except Exception as exc:
                    raise DurableExecutionError('audit_unavailable') from exc
            await self._journal.start(execution.id)
            try:
                result = await invoke()
            except asyncio.CancelledError:
                await self._journal.unknown(execution.id, 'cancelled')
                raise
            except ToolExecutionError as exc:
                code = exc.code
            except TimeoutError:
                code = 'tool_timeout'
            except Exception:
                code = 'executor_error'
            else:
                await self._journal.complete(execution.id, result)
                return result

            if request.risk_level != 'read_only':
                # The effect may have happened; never retry a mutating tool blindly.
                await self._journal.unknown(execution.id, code)
                raise DurableExecutionError(code)
            await self._journal.fail(execution.id, code)
            if code not in RETRYABLE_CODES or execution.attempt >= request.max_attempts:
                raise DurableExecutionError(code)


def context_correlation(request: ToolExecutionRequest) -> UUID:
    # Legacy callers without correlation still get a deterministic, non-secret ID.
    return request.run_id


class ExecutionConflict(DurableExecutionError):
    def __init__(self):
        super().__init__('execution_conflict')


class ExecutionNotFound(DurableExecutionError):
    def __init__(self):
        super().__init__('execution_not_found')


class GatewayExecutionJournal:
    def __init__(self, base_url: str, internal_key: str, *, timeout: float = 5,
                 transport: httpx.AsyncBaseTransport | None = None):
        self._base = base_url.rstrip('/')
        self._headers = {'Authorization': f'Bearer {internal_key}'}
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def _request(self, method: str, path: str, body: dict | None = None) -> ToolExecution:
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self._transport, timeout=self._timeout,
                                             follow_redirects=False, trust_env=False)
        response = await self._client.request(method, self._base + path, json=body, headers=self._headers)
        if response.status_code == 409:
            raise ExecutionConflict()
        if response.status_code == 404:
            raise ExecutionNotFound()
        if response.status_code != 200:
            raise DurableExecutionError('execution_journal_error')
        return ToolExecution.model_validate(response.json())

    async def reserve(self, request: ToolExecutionRequest) -> ToolExecution:
        return await self._request('POST', '/internal/v1/tool-executions/reserve',
                                   request.model_dump(mode='json'))

    async def start(self, execution_id: UUID) -> ToolExecution:
        return await self._request('POST', f'/internal/v1/tool-executions/{execution_id}/start')

    async def complete(self, execution_id: UUID, result: JsonValue) -> ToolExecution:
        return await self._request('POST', f'/internal/v1/tool-executions/{execution_id}/complete',
                                   {'result': result})

    async def fail(self, execution_id: UUID, code: str) -> ToolExecution:
        return await self._request('POST', f'/internal/v1/tool-executions/{execution_id}/fail',
                                   {'error_code': code})

    async def unknown(self, execution_id: UUID, code: str) -> ToolExecution:
        return await self._request('POST', f'/internal/v1/tool-executions/{execution_id}/unknown',
                                   {'error_code': code})

    async def reconcile(self, execution_id: UUID, status: str, *,
                        result: JsonValue | None = None, error_code: str | None = None) -> ToolExecution:
        body = {'status': status}
        if result is not None:
            body['result'] = result
        if error_code is not None:
            body['error_code'] = error_code
        return await self._request('POST', f'/internal/v1/tool-executions/{execution_id}/reconcile', body)

    async def get(self, execution_id: UUID) -> ToolExecution:
        return await self._request('GET', f'/internal/v1/tool-executions/{execution_id}')

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
