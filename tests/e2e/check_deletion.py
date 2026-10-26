"""Conversation deletion, tombstone audit and repeatable retention sweep."""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
ADMIN = os.environ['UAI_TEST_KEY']
INTERNAL = os.environ['UAI_TEST_INTERNAL_KEY']


def request(path, *, method='GET', body=None, key=ADMIN, headers=None):
    request_headers = {'Authorization': 'Bearer ' + key}
    if body is not None:
        request_headers['Content-Type'] = 'application/json'
    if headers:
        request_headers.update(headers)
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


status, raw = request('/v1/assistants', method='POST', body={
    'name': 'Deletion E2E', 'model': 'test', 'system_prompt': 'Helpful',
})
assert status == 201, (status, raw)
assistant = json.loads(raw)['id']
status, raw = request('/v1/conversations', method='POST', body={'assistant_id': assistant})
assert status == 201, (status, raw)
conversation = json.loads(raw)['id']
status, stream = request(
    f'/v1/conversations/{conversation}/messages',
    method='POST', body={'content': 'Da cancellare'},
    headers={'Idempotency-Key': 'deletion-e2e'},
)
assert status == 200, stream
events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
assert events[-1]['event_type'] == 'response.completed', events
run_id = events[-1]['run_id']

status, raw = request(f'/v1/conversations/{conversation}', method='DELETE')
assert status == 204, (status, raw)
assert request(f'/v1/conversations/{conversation}/messages')[0] == 404
assert request(f'/v1/agent-runs/{run_id}')[0] == 404
assert request(f'/v1/conversations/{conversation}', method='DELETE')[0] == 404

status, raw = request(f'/v1/audit-events?target_id={conversation}')
assert status == 200, (status, raw)
assert any(event['action'] == 'conversation.deleted' for event in json.loads(raw)), raw

status, raw = request('/internal/v1/retention/run', method='POST', key=INTERNAL, body={})
assert status == 200, (status, raw)
result = json.loads(raw)
assert set(result) == {'conversations', 'approvals', 'audit_events', 'cleanup_jobs'}, result
status, raw = request('/internal/v1/retention/run', method='POST', key=INTERNAL, body={})
assert status == 200, (status, raw)
print('E2E deletion/tombstone/retention: passed')
