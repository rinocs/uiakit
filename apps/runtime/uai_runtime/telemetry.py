"""ASGI telemetry middleware for the private runtime."""
from __future__ import annotations

import time

from uai_core.telemetry import configure_telemetry, current_trace_id, get_telemetry, sanitize_route


class TelemetryMiddleware:
    def __init__(self, app, service: str = 'uai-runtime'):
        self.app = app
        self.service = service
        self.telemetry = configure_telemetry(service)

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http':
            await self.app(scope, receive, send)
            return
        from opentelemetry.propagate import extract
        from opentelemetry.trace import SpanKind

        headers = {key.decode('latin-1').lower(): value.decode('latin-1')
                   for key, value in scope.get('headers', [])}
        parent = extract(headers)
        route = sanitize_route(scope.get('path', '/'))
        started = time.monotonic()
        status = 500
        with self.telemetry.span(f'{scope.get("method", "GET")} {route}',
                                 {'http.method': scope.get('method', 'GET'), 'http.route': route},
                                 context=parent) as span:
            async def send_wrapper(message):
                nonlocal status
                if message['type'] == 'http.response.start':
                    status = int(message.get('status', 500))
                    if span is not None:
                        span.set_attribute('http.status_code', status)
                    trace_id = current_trace_id()
                    if trace_id:
                        message = dict(message)
                        message['headers'] = list(message.get('headers', [])) + [
                            (b'x-trace-id', trace_id.encode()),
                        ]
                await send(message)

            await self.app(scope, receive, send_wrapper)
            self.telemetry.record_request(scope.get('method', 'GET'), route, status,
                                          time.monotonic() - started)


def telemetry():
    return get_telemetry('uai-runtime')
