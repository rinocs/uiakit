"""Optional OpenTelemetry instrumentation shared by runtime and worker.

No endpoint means a no-op tracer/meter: telemetry never blocks a request and
never changes application semantics. Attributes are allow-listed by dropping
prompt/credential-like keys and bounding cardinality.
"""
from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator

SENSITIVE = ('prompt', 'message', 'content', 'authorization', 'cookie', 'token',
             'password', 'secret', 'api_key', 'apikey', 'credential')
_UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')


def sanitize_attributes(attributes: dict[str, Any] | None) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in (attributes or {}).items():
        lowered = key.lower()
        if any(word in lowered for word in SENSITIVE):
            continue
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', lowered):
            continue
        if isinstance(value, bool):
            safe[key] = 'true' if value else 'false'
        elif isinstance(value, (int, float, str)):
            safe[key] = str(value)[:200]
    return safe


def sanitize_route(path: str) -> str:
    path = _UUID.sub('{id}', path)
    return re.sub(r'/[0-9]+}', '/{id}', path)


class Telemetry:
    def __init__(self, service: str, *, tracer=None, meter=None):
        self.service = service
        self.enabled = tracer is not None or meter is not None
        self.tracer = tracer
        self.request_counter = None
        self.request_duration = None
        self.event_counter = None
        self.token_counter = None
        self.cost_counter = None
        self.error_counter = None
        if meter is not None:
            self.request_counter = meter.create_counter('uai.requests', unit='1')
            self.request_duration = meter.create_histogram('uai.request.duration', unit='s')
            self.event_counter = meter.create_counter('uai.events', unit='1')
            self.token_counter = meter.create_counter('uai.tokens', unit='1')
            self.cost_counter = meter.create_counter('uai.cost', unit='USD')
            self.error_counter = meter.create_counter('uai.errors', unit='1')

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None, *,
             context=None) -> Iterator[Any]:
        if self.tracer is None:
            yield None
            return
        with self.tracer.start_as_current_span(
            name, context=context, attributes=sanitize_attributes(attributes),
            record_exception=False, set_status_on_exception=False,
        ) as span:
            started = time.monotonic()
            outcome = 'ok'
            try:
                yield span
            except BaseException:
                outcome = 'error'
                raise
            finally:
                if self.request_duration is not None:
                    self.request_duration.record(
                        time.monotonic() - started,
                        {'service': self.service, 'operation': name, 'outcome': outcome},
                    )

    def record_event(self, event_type: str, *, terminal: bool = False) -> None:
        if self.event_counter is not None:
            self.event_counter.add(1, {'service': self.service, 'event_type': event_type,
                                       'terminal': 'true' if terminal else 'false'})

    def record_tokens(self, model: str, input_tokens: int, output_tokens: int) -> None:
        if self.token_counter is None:
            return
        model = model[:100]
        if input_tokens:
            self.token_counter.add(input_tokens, {'service': self.service, 'model': model, 'direction': 'input'})
        if output_tokens:
            self.token_counter.add(output_tokens, {'service': self.service, 'model': model, 'direction': 'output'})

    def record_cost(self, model: str, input_tokens: int, output_tokens: int) -> None:
        if self.cost_counter is None:
            return
        try:
            input_rate = float(os.environ.get('UAI_MODEL_COST_INPUT_PER_MILLION', '0'))
            output_rate = float(os.environ.get('UAI_MODEL_COST_OUTPUT_PER_MILLION', '0'))
        except ValueError:
            return
        if input_rate < 0 or output_rate < 0:
            return
        model = model[:100]
        if input_rate and input_tokens:
            self.cost_counter.add(input_tokens * input_rate / 1_000_000,
                                  {'service': self.service, 'model': model, 'direction': 'input'})
        if output_rate and output_tokens:
            self.cost_counter.add(output_tokens * output_rate / 1_000_000,
                                  {'service': self.service, 'model': model, 'direction': 'output'})

    def record_error(self, code: str, operation: str) -> None:
        if self.error_counter is not None:
            self.error_counter.add(1, {'service': self.service, 'code': code[:100],
                                       'operation': operation[:100]})

    def record_request(self, method: str, route: str, status: int, seconds: float) -> None:
        attrs = {'service': self.service, 'method': method, 'route': sanitize_route(route),
                 'status': str(status)}
        if self.request_counter is not None:
            self.request_counter.add(1, attrs)
        if self.request_duration is not None:
            self.request_duration.record(seconds, {'service': self.service, 'route': attrs['route'],
                                                   'status': str(status)})


telemetry: Telemetry | None = None
_configured = False


def configure_telemetry(service: str) -> Telemetry:
    global telemetry, _configured
    if telemetry is not None:
        return telemetry
    endpoint = os.environ.get('UAI_OTEL_ENDPOINT') or os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')
    if not endpoint or _configured:
        telemetry = Telemetry(service)
        _configured = True
        return telemetry
    _configured = True
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        resource = Resource.create({SERVICE_NAME: service})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(tracer_provider)
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))],
        )
        metrics.set_meter_provider(meter_provider)
        set_global_textmap(TraceContextTextMapPropagator())
        telemetry = Telemetry(service, tracer=trace.get_tracer(service), meter=metrics.get_meter(service))
    except Exception:
        # Exporter/dependency failures are fail-open: keep serving requests.
        telemetry = Telemetry(service)
    return telemetry


def get_telemetry(service: str = 'uai') -> Telemetry:
    return telemetry or configure_telemetry(service)


def current_trace_id() -> str:
    try:
        from opentelemetry import trace
        context = trace.get_current_span().get_span_context()
        return format(context.trace_id, '032x') if context.is_valid else ''
    except Exception:
        return ''
