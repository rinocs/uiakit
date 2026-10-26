"""Redacted, structured audit events for runtime-side sensitive actions.

The gateway PostgreSQL trail is authoritative. This module is the runtime-side
record used before a tool effect: it never accepts headers, arguments, results or
prompts, and fails closed if the event cannot be serialized.
"""
import json
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


SENSITIVE_KEYS = frozenset({
    'authorization', 'proxy_authorization', 'cookie', 'set_cookie', 'x_api_key',
    'api_key', 'apikey', 'token', 'access_token', 'refresh_token', 'id_token',
    'password', 'passwd', 'client_secret', 'secret', 'private_key', 'key_digest',
    'credential', 'credentials', 'policy_snapshot', 'system_prompt', 'prompt',
    'messages', 'content', 'arguments', 'result', 'body', 'headers',
    'request_body', 'response_body',
})
_KIND = re.compile(r'^[a-z][a-z0-9_.-]{0,99}$')
_DIGEST = re.compile(r'^[0-9a-f]{64}$')


def _sensitive(key: str) -> bool:
    normalized = key.lower().replace('-', '_')
    return (normalized in SENSITIVE_KEYS or 'secret' in normalized
            or 'password' in normalized or 'token' in normalized
            or 'authorization' in normalized or 'cookie' in normalized)


def redact_details(value: Any) -> Any:
    """Return a JSON-safe copy with sensitive keys replaced, never dropped silently."""
    if isinstance(value, Mapping):
        return {key: ('[redacted]' if _sensitive(str(key)) else redact_details(item))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_details(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return '[redacted]'


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    action: str = Field(pattern=_KIND.pattern)
    actor_id: str = Field(min_length=1, max_length=200)
    target_id: UUID
    run_id: UUID
    correlation_id: UUID
    digest: str | None = Field(default=None, pattern=_DIGEST.pattern)
    outcome: str = Field(pattern=_KIND.pattern)
    details: dict[str, JsonValue] = Field(default_factory=dict)


class AuditSink(Protocol):
    def record(self, payload: dict[str, Any]) -> None: ...


def _log_event(payload: dict[str, Any]) -> None:
    logging.getLogger('uai.audit').info(json.dumps(payload, sort_keys=True,
                                                   separators=(',', ':')))


class AuditLog:
    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None):
        self._sink = sink or _log_event

    def record(self, event: AuditEvent) -> None:
        payload = event.model_dump(mode='json')
        payload['details'] = redact_details(event.details)
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(encoded.encode('utf-8')) > 16384:
            raise ValueError('audit_event_too_large')
        self._sink(payload)
