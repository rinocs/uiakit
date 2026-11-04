"""Trace propagation gateway→runtime and fail-open behavior without a collector."""
from __future__ import annotations

import json
import os
import secrets
import urllib.error
import uuid
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
ADMIN = os.environ['UAI_TEST_KEY']


def request(path, *, method='GET', body=None, headers=None):
    merged = {'Authorization': 'Bearer ' + ADMIN}
    if body is not None:
        merged['Content-Type'] = 'application/json'
    if headers:
        merged.update(headers)
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=merged, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode()


trace_id = secrets.token_hex(16)
span_id = secrets.token_hex(8)
traceparent = f'00-{trace_id}-{span_id}-01'
status, headers, raw = request('/v1/health', headers={'traceparent': traceparent})
assert status == 200, (status, raw)
assert headers.get('X-Trace-ID') == trace_id, (trace_id, headers.get('X-Trace-ID'))

status, _, raw = request('/v1/assistants', method='POST', body={
    'name': 'Observability E2E', 'model': 'test', 'system_prompt': 'Helpful',
}, headers={'traceparent': traceparent})
assert status == 201, (status, raw)
assistant = json.loads(raw)['id']
status, _, raw = request('/v1/conversations', method='POST', body={'assistant_id': assistant},
                         headers={'traceparent': traceparent})
assert status == 201, (status, raw)
conversation = json.loads(raw)['id']
status, headers, stream = request(
    f'/v1/conversations/{conversation}/messages', method='POST',
    body={'content': 'Ciao osservabilità'},
    headers={'traceparent': traceparent, 'Idempotency-Key': 'observability-e2e'},  # gitleaks:allow -- synthetic idempotency marker, not a credential
)
assert status == 200, (status, stream)
assert headers.get('X-Trace-ID') == trace_id, (trace_id, headers.get('X-Trace-ID'))
events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
assert events[-1]['event_type'] == 'response.completed', events
print('E2E OpenTelemetry propagation/fail-open: passed')
