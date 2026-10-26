"""Mandatory built-ins through the public gateway and real persistence."""
import json
import os
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
            return response.status, response.read().decode()
    except HTTPError as response:
        return response.code, response.read().decode()


def frames(raw):
    return [json.loads(line.removeprefix('data:').strip())
            for line in raw.splitlines() if line.startswith('data:')]


guards = ['builtin.system_prompt', 'builtin.conversation_memory', 'builtin.tool_policy',
          'builtin.output_validation', 'builtin.observability']
status, raw = request('/v1/assistants', {'name': 'Built-ins', 'model': 'test',
                                      'system_prompt': 'Helpful', 'directives': guards})
assert status == 201
assistant = json.loads(raw)['id']
status, raw = request('/v1/conversations', {'assistant_id': assistant})
assert status == 201
messages = '/v1/conversations/' + json.loads(raw)['id'] + '/messages'
status, raw = request(messages, {'content': 'With required guards'}, headers={'Idempotency-Key': 'builtin-valid'})
assert status == 200 and frames(raw)[-1]['event_type'] == 'response.completed'
# Empty optional selection cannot disable output validation.
assert request('/v1/assistants/' + assistant, {'directives': []}, method='PATCH', headers={'If-Match': '"1"'})[0] == 200
status, raw = request(messages, {'content': '__e2e_whitespace__'}, headers={'Idempotency-Key': 'builtin-invalid-output'})
assert status == 200 and frames(raw)[-1]['payload']['code'] == 'directive_failed'
assert all(e['event_type'] != 'response.completed' for e in frames(raw))
# Even a middleware with a very late priority runs before mandatory validators.
assert request('/v1/assistants/' + assistant, {'directives': ['e2e.foreign_history']},
               method='PATCH', headers={'If-Match': '"2"'})[0] == 200
status, raw = request(messages, {'content': 'History attack'}, headers={'Idempotency-Key': 'builtin-foreign-history'})
assert status == 200
assert [e['event_type'] for e in frames(raw)] == ['agent.started', 'agent.failed']
assert frames(raw)[-1]['payload']['code'] == 'directive_failed'
assert 'unauthorized fixture history' not in raw
assert request(messages, {'content': 'History attack'}, headers={'Idempotency-Key': 'builtin-foreign-history'})[1] == raw
print('E2E built-in selection, required output validation and final history guards: passed')
