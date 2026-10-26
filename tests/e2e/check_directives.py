"""Public selection, durable versions, replay and after-model rejection in Docker."""
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
KEY = os.environ['UAI_TEST_KEY']


def request(path, body=None, *, method=None, headers=None):
    req = Request(BASE + path, method=method,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json',
                           **(headers or {})})
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def frames(raw):
    return [json.loads(line.removeprefix('data:').strip())
            for line in raw.splitlines() if line.startswith('data:')]


config = {'name': 'Directives E2E', 'model': 'test', 'system_prompt': 'Helpful',
          'directives': ['e2e.prefix']}
assert request('/v1/assistants', {**config, 'directives': ['unregistered']})[0] == 422
status, headers, raw = request('/v1/assistants', config)
assert status == 201 and headers['ETag'] == '"1"'
assistant = json.loads(raw)['id']
path = '/v1/assistants/' + assistant
status, _, raw = request('/v1/conversations', {'assistant_id': assistant})
assert status == 201
messages = '/v1/conversations/' + json.loads(raw)['id'] + '/messages'
turn = {'content': 'Selected directive'}
status, headers, original = request(messages, turn, headers={'Idempotency-Key': 'directive-first'})
assert status == 200 and headers['X-Assistant-Version'] == '1'
first_run = headers['X-Run-ID']
assert frames(original)[-1]['payload']['text'] == 'Risposta mock: E2E directive: Selected directive'
for invalid in [['unknown'], ['e2e.reject'], ['e2e.prefix', 'e2e.prefix']]:
    assert request(path, {'directives': invalid}, method='PATCH', headers={'If-Match': '"1"'})[0] == 422
assert request(path)[1]['ETag'] == '"1"'
status, headers, _ = request(path, {'directives': []}, method='PATCH', headers={'If-Match': '"1"'})
assert status == 200 and headers['ETag'] == '"2"'
status, headers, replay = request(messages, turn, headers={'Idempotency-Key': 'directive-first'})
assert status == 200 and headers['X-Assistant-Version'] == '1' and replay == original
status, headers, raw = request(messages, {'content': 'No directive'}, headers={'Idempotency-Key': 'directive-second'})
assert status == 200 and headers['X-Assistant-Version'] == '2'
second_run = headers['X-Run-ID']
assert frames(raw)[-1]['payload']['text'] == 'Risposta mock: No directive'
status, _, raw = request(path + '/versions')
versions = json.loads(raw)
assert status == 200 and [v['directives'] for v in versions] == [['e2e.prefix'], []]
status, _, _ = request(path, {'directives': ['e2e.prefix', 'e2e.reject']},
                       method='PATCH', headers={'If-Match': '"2"'})
assert status == 200
turn = {'content': 'Rejected completion'}
status, rejected_headers, rejected = request(messages, turn, headers={'Idempotency-Key': 'directive-rejected'})
assert status == 200
assert frames(rejected)[-1]['event_type'] == 'agent.failed'
assert frames(rejected)[-1]['payload']['code'] == 'directive_failed'
assert all(event['event_type'] != 'response.completed' for event in frames(rejected))
assert 'private fixture diagnostic' not in rejected
assert request(messages, turn, headers={'Idempotency-Key': 'directive-rejected'})[2] == rejected
print('E2E directives, versions, replay and rejection: passed')

if len(sys.argv) > 1:
    Path(sys.argv[1]).write_text(json.dumps({
        first_run: 'response.completed', second_run: 'response.completed',
        rejected_headers['X-Run-ID']: 'agent.failed'}))
