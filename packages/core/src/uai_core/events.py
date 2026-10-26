"""Typed lifecycle events; the public v1 SSE envelope remains unchanged."""
from datetime import datetime, timezone
from typing import Any, Literal
from types import MappingProxyType
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .retrieval import Citation

RuntimeEventType = Literal['agent.started', 'response.delta', 'response.completed', 'agent.failed', 'agent.cancelled']


class StartedPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TextPayload(StartedPayload):
    text: str = Field(min_length=1)


class CompletedPayload(TextPayload):
    usage: dict[str, int] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)


class FailedPayload(StartedPayload):
    code: str = Field(min_length=1)


class CancelledPayload(StartedPayload):
    code: str = Field(default='cancelled', min_length=1)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID = Field(default_factory=uuid4)
    event_version: Literal[1] = 1
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: UUID
    correlation_id: UUID


class RuntimeEvent(EventEnvelope):
    event_type: RuntimeEventType
    payload: StartedPayload | TextPayload | CompletedPayload | FailedPayload

    @model_validator(mode='before')
    @classmethod
    def payload_matches_phase(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload_types = {'agent.started': StartedPayload, 'response.delta': TextPayload,
                             'response.completed': CompletedPayload, 'agent.failed': FailedPayload,
                             'agent.cancelled': CancelledPayload}
            kind = data.get('event_type')
            if kind in payload_types:
                data = dict(data)
                data['payload'] = payload_types[kind].model_validate(data.get('payload'))
        return data

    def sse(self) -> str:
        return f'id: {self.event_id}\nevent: {self.event_type}\ndata: {self.model_dump_json()}\n\n'


# Observability has its own contract: subscribers never receive model text,
# prompts, arguments, authorization objects or the mutable working memory.
LifecycleEventType = Literal[
    'request.received', 'request.authorized', 'agent.started', 'context.building',
    'context.ready', 'model.before', 'model.after', 'tool.requested',
    'tool.authorized', 'tool.started', 'tool.completed', 'tool.failed',
    'memory.read', 'memory.write', 'response.delta', 'response.completed',
    'agent.failed', 'agent.cancelled',
]


class ObservationPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ContextMetrics(ObservationPayload):
    message_count: int = Field(ge=1, le=100)
    input_chars: int = Field(ge=0)


class ModelObservation(ObservationPayload):
    model: str = Field(min_length=1, max_length=200)


class OutputMetrics(ObservationPayload):
    output_chars: int = Field(ge=0)


class ToolObservation(ObservationPayload):
    tool_id: str = Field(min_length=1, max_length=200)


class ToolOutput(ToolObservation):
    output_chars: int = Field(ge=0)


class FailureObservation(ObservationPayload):
    code: str = Field(pattern=r'^[a-z][a-z0-9_]{0,99}$')


class ToolFailure(ToolObservation, FailureObservation):
    pass


class MemoryObservation(ObservationPayload):
    scope: Literal['working', 'conversation', 'semantic']
    entries: int = Field(ge=0)


class ResponseMetrics(ObservationPayload):
    characters: int = Field(gt=0)


class CancellationObservation(ObservationPayload):
    reason: Literal['cancelled', 'closed']


LIFECYCLE_PAYLOADS = MappingProxyType({
    'request.received': ContextMetrics, 'request.authorized': ObservationPayload,
    'agent.started': ObservationPayload, 'context.building': ObservationPayload,
    'context.ready': ContextMetrics, 'model.before': ModelObservation,
    'model.after': OutputMetrics, 'tool.requested': ToolObservation,
    'tool.authorized': ToolObservation, 'tool.started': ToolObservation,
    'tool.completed': ToolOutput, 'tool.failed': ToolFailure,
    'memory.read': MemoryObservation, 'memory.write': MemoryObservation,
    'response.delta': ResponseMetrics, 'response.completed': ResponseMetrics,
    'agent.failed': FailureObservation, 'agent.cancelled': CancellationObservation,
})


def _lifecycle_schema(schema: dict) -> None:
    # JSON Schema must enforce the same phase/payload pairing as Python.
    schema['allOf'] = [
        {'if': {'properties': {'event_type': {'const': kind}}},
         'then': {'properties': {'payload': payload.model_json_schema()}}}
        for kind, payload in LIFECYCLE_PAYLOADS.items()
    ]


class LifecycleEvent(EventEnvelope):
    """Detached metadata-only observation, independent of public SSE payloads."""
    model_config = ConfigDict(extra='forbid', frozen=True, json_schema_extra=_lifecycle_schema)
    event_type: LifecycleEventType
    payload: (ContextMetrics | ModelObservation | OutputMetrics | ToolOutput | ToolFailure
              | ToolObservation | MemoryObservation | ResponseMetrics | FailureObservation
              | CancellationObservation | ObservationPayload)

    @model_validator(mode='before')
    @classmethod
    def payload_matches_phase(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get('event_type') in LIFECYCLE_PAYLOADS:
            data = dict(data)
            data['payload'] = LIFECYCLE_PAYLOADS[data['event_type']].model_validate(data.get('payload'))
        return data

    @classmethod
    def from_runtime(cls, event: RuntimeEvent) -> 'LifecycleEvent':
        """Keep event identity while replacing private response text with metrics."""
        if event.event_type in ('response.delta', 'response.completed'):
            payload = {'characters': len(event.payload.text)}
        elif event.event_type == 'agent.failed':
            payload = {'code': event.payload.code}
        elif event.event_type == 'agent.cancelled':
            payload = {'reason': 'cancelled'}
        else:
            payload = {}
        return cls(event_id=event.event_id, event_version=event.event_version,
                   timestamp=event.timestamp, event_type=event.event_type,
                   run_id=event.run_id, correlation_id=event.correlation_id, payload=payload)
