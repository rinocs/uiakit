"""Durable tool reservation, replay, retry and unknown states through the internal gateway API."""
import json
import os
import sys
import threading
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
KEY = os.environ['UAI_TEST_INTERNAL_KEY']
RUN = json.load(open(sys.argv[1]))['runs'][0]


def request(path, body=None, method=None, key=KEY):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method or ('POST' if body is not None else 'GET'))
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode()
    except HTTPError as response:
        return response.code, response.read().decode()


def payload(key, risk='read_only', approval=None):
    body = {'run_id': RUN, 'tool_id': 'test.read', 'tool_version': '1.0.0',
            'arguments_digest': 'a' * 64, 'risk_level': risk,
            'idempotency_key': key, 'max_attempts': 2}
    if risk != 'read_only':
        body['max_attempts'] = 1
    if approval is not None:
        body['approval_id'] = approval
    return body


assert request('/internal/v1/tool-executions/reserve', payload('auth'), key='wrong')[0] == 401

status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-1'))
assert status == 200 and json.loads(raw)['status'] == 'reserved', (status, raw)
execution = json.loads(raw)['id']
assert request('/internal/v1/tool-executions/' + execution + '/start', {})[0] == 200
status, raw = request('/internal/v1/tool-executions/' + execution + '/complete', {'result': {'ok': True}})
assert status == 200 and json.loads(raw)['status'] == 'completed', (status, raw)
status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-1'))
assert status == 200 and json.loads(raw)['status'] == 'completed' and json.loads(raw)['result'] == {'ok': True}

codes = []
def reserve():
    codes.append(request('/internal/v1/tool-executions/reserve', payload('exec-e2e-concurrent'))[0])

threads = [threading.Thread(target=reserve) for _ in range(2)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
assert sorted(codes) == [200, 409], codes

status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-retry'))
retry = json.loads(raw)['id']
assert status == 200
assert request('/internal/v1/tool-executions/' + retry + '/start', {})[0] == 200
assert request('/internal/v1/tool-executions/' + retry + '/fail', {'error_code': 'tool_timeout'})[0] == 200
status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-retry'))
assert status == 200 and json.loads(raw)['status'] == 'reserved' and json.loads(raw)['attempt'] == 2, (status, raw)
assert request('/internal/v1/tool-executions/' + retry + '/start', {})[0] == 200
assert request('/internal/v1/tool-executions/' + retry + '/unknown', {'error_code': 'effect_unknown'})[0] == 200
status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-retry'))
assert status == 200 and json.loads(raw)['status'] == 'unknown'
status, raw = request('/internal/v1/tool-executions/' + retry + '/reconcile',
                     {'status': 'completed', 'result': {'reconciled': True}})
assert status == 200 and json.loads(raw)['status'] == 'completed', (status, raw)
status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-retry'))
assert status == 200 and json.loads(raw)['status'] == 'completed' and json.loads(raw)['result'] == {'reconciled': True}

status, raw = request('/internal/v1/tool-executions/reserve', payload('exec-e2e-write', 'write'))
assert status == 422, (status, raw)
print('Durable tool execution reserve/replay/retry/unknown: passed')
