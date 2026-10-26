"""Public agent-run list/get/cancel, terminal transition and SSE replay."""
import json
import os
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, KEY = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY']


def request(path, body=None, method=None, key=KEY):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


status, _, raw = request('/v1/assistants', {'name': 'Run E2E', 'model': 'test', 'system_prompt': 'Helpful'})
assert status == 201, (status, raw)
assistant = json.loads(raw)
status, _, raw = request('/v1/conversations', {'assistant_id': assistant['id']})
assert status == 201, (status, raw)
conversation = json.loads(raw)['id']
path = '/v1/conversations/' + conversation + '/messages'
result = {}


def run_message():
    req = Request(BASE + path, data=json.dumps({'content': '__e2e_slow__'}).encode(),
                  headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json',
                           'Idempotency-Key': 'run-cancel-e2e'})
    try:
        with urlopen(req, timeout=60) as response:
            result['status'] = response.status
            result['text'] = response.read().decode()
    except Exception as error:
        result['error'] = repr(error)


thread = threading.Thread(target=run_message)
thread.start()
run = None
for _ in range(30):
    status, _, raw = request('/v1/agent-runs')
    if status == 200:
        for candidate in json.loads(raw):
            if candidate['conversation_id'] == conversation and candidate['status'] == 'running':
                run = candidate
                break
    if run:
        break
    time.sleep(0.2)
assert run, 'running agent run not found'
assert request('/v1/agent-runs/' + run['id'])[0] == 200
status, _, raw = request('/v1/agent-runs/' + run['id'] + '/cancel', method='POST')
assert status == 200 and json.loads(raw)['status'] == 'cancelled', (status, raw)
thread.join(timeout=30)
assert 'text' in result, result
assert 'agent.cancelled' in result['text'], result['text'][-500:]
assert request('/v1/agent-runs/' + run['id'])[0] == 200
status, _, raw = request('/v1/agent-runs/' + run['id'])
assert json.loads(raw)['status'] == 'cancelled'
assert request('/v1/agent-runs/' + run['id'] + '/cancel', method='POST')[0] == 409
# Replay uses the same idempotency key through a direct request.
req = Request(BASE + path, data=json.dumps({'content': '__e2e_slow__'}).encode(),
              headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json',
                       'Idempotency-Key': 'run-cancel-e2e'})
with urlopen(req, timeout=30) as response:
    replay = response.read().decode()
assert 'agent.cancelled' in replay and replay == result['text']
print('Agent run state, cancellation, terminal transition and replay: passed')
