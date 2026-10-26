"""Human approval binding, scope, expiry, rejection and concurrent decision checks."""
import json
import os
import sys
import threading
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, KEY = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY']
STATE = Path(sys.argv[2])


def request(path, body=None, method=None, key=KEY):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode()
    except HTTPError as response:
        return response.code, response.read().decode()


if sys.argv[1] == 'seed':
    status, raw = request('/v1/assistants', {'name': 'Approval E2E', 'model': 'test',
                                             'system_prompt': 'Helpful'})
    assert status == 201, (status, raw)
    assistant = json.loads(raw)['id']
    conversations, runs, approvals = [], [], []
    for _ in range(3):
        status, raw = request('/v1/conversations', {'assistant_id': assistant})
        assert status == 201, (status, raw)
        conversations.append(json.loads(raw)['id'])
        runs.append(str(uuid.uuid4()))
        approvals.append(str(uuid.uuid4()))
    STATE.write_text(json.dumps({'assistant': assistant, 'conversations': conversations,
                                 'runs': runs, 'approvals': approvals}))
    print('Approval seed state written')
else:
    state = json.loads(STATE.read_text())
    run, expired_run, rejected_run = state['runs']
    approval, expired, rejected = state['approvals']

    status, raw = request('/v1/approvals')
    assert status == 200, (status, raw)
    entries = json.loads(raw)
    assert any(item['id'] == approval and item['run_id'] == run for item in entries), entries
    item = next(item for item in entries if item['id'] == approval)
    assert item['status'] == 'pending' and item['tool_version'] == '1.0.0'
    assert item['arguments_digest'] == 'a' * 64 and item['policy_digest'] == 'b' * 64
    assert 'arguments' not in item and 'secret' not in json.dumps(item)
    assert request('/v1/approvals/' + approval)[0] == 200

    codes = []
    def approve():
        codes.append(request('/v1/approvals/' + approval + '/approve', method='POST')[0])

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == [200, 409], codes
    status, raw = request('/v1/approvals/' + approval)
    assert status == 200 and json.loads(raw)['status'] == 'approved', raw
    status, raw = request('/v1/agent-runs/' + run)
    assert status == 200 and json.loads(raw)['status'] == 'running', raw
    assert request('/v1/approvals/' + approval + '/approve', method='POST')[0] == 409

    status, raw = request('/v1/approvals/' + expired + '/approve', method='POST')
    assert status == 409, (status, raw)
    status, raw = request('/v1/approvals/' + expired)
    assert status == 200 and json.loads(raw)['status'] == 'expired', raw

    status, raw = request('/v1/approvals/' + rejected + '/reject', method='POST')
    assert status == 200 and json.loads(raw)['status'] == 'rejected', (status, raw)
    status, raw = request('/v1/agent-runs/' + rejected_run)
    assert status == 200 and json.loads(raw)['status'] == 'failed', raw

    status, raw = request('/v1/audit-events?run_id=' + run)
    assert status == 200, (status, raw)
    audit = json.loads(raw)
    entry = next(item for item in audit if item['action'] == 'approval.approved')
    assert entry['run_id'] == run and entry['digest'] == 'a' * 64
    assert entry['outcome'] == 'approved' and entry['correlation_id']
    assert 'authorization' not in raw.lower() and 'bearer' not in raw.lower()

    status, raw = request('/v1/credentials', {'role': 'operator', 'scopes': ['approvals:read']})
    assert status == 201, (status, raw)
    reader_key = json.loads(raw)['api_key']
    assert request('/v1/approvals', key=reader_key)[0] == 200
    assert request('/v1/approvals/' + approval + '/approve', method='POST', key=reader_key)[0] == 403
    assert request('/v1/audit-events', key=reader_key)[0] == 403
    print('Approval decision, scope, expiry, rejection, audit and run resume: passed')
