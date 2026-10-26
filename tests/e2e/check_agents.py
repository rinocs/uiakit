"""End-to-end agent tool loop against the real mock HTTP tool and gateway journal."""
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ.get('UAI_TEST_URL', 'http://gateway:8080')
KEY = os.environ['UAI_TEST_KEY']
TOOL = os.environ.get('MOCK_TOOL_URL', 'http://mock-tool:9100')


def request(path, body=None, method=None, key=KEY, idem=None):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    if idem:
        headers['Idempotency-Key'] = idem
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def stats():
    with urlopen(TOOL + '/stats', timeout=5) as response:
        return json.loads(response.read().decode())


def frames(raw):
    return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ')]


def assistant(tools, limits=None):
    body = {'name': 'Agent E2E', 'model': 'test', 'system_prompt': 'Use the selected tool.',
            'tools': tools}
    if limits:
        body['limits'] = limits
    status, _, raw = request('/v1/assistants', body)
    assert status == 201, (status, raw)
    return json.loads(raw)['id']


def conversation(assistant_id):
    status, _, raw = request('/v1/conversations', {'assistant_id': assistant_id})
    assert status == 201, (status, raw)
    return json.loads(raw)['id']


def message(conversation_id, content, idem):
    status, _, raw = request('/v1/conversations/' + conversation_id + '/messages',
                             {'content': content}, idem=idem)
    assert status == 200, (status, raw)
    events = frames(raw)
    assert events and events[0]['event_type'] == 'agent.started'
    assert events[-1]['event_type'] in ('response.completed', 'agent.failed')
    return events


read_agent = assistant(['mocktool.read'])
read_chat = conversation(read_agent)
before = stats()
events = message(read_chat, '__e2e_tool_read__', 'agent-e2e-read')
assert events[-1]['event_type'] == 'response.completed', events[-1]
assert 'Tool result:' in events[-1]['payload']['text']
assert events[-1]['payload']['text'].count('hello') == 1
after = stats()
assert after['reads'] == before['reads'] + 1, (before, after)
assert after['writes'] == before['writes']

run_id = events[0]['run_id']
status, _, raw = request('/v1/audit-events?run_id=' + run_id)
assert status == 200, (status, raw)
audit = json.loads(raw)
assert any(item['action'] == 'tool_execution.completed' for item in audit), audit
assert all('authorization' not in json.dumps(item['details']).lower() for item in audit)

before = stats()
events = message(read_chat, '__e2e_tool_unauthorized__', 'agent-e2e-unauthorized')
assert events[-1]['event_type'] == 'agent.failed' and events[-1]['payload']['code'] == 'tool_not_authorized'
after = stats()
assert after['writes'] == before['writes'], (before, after)

storm_agent = assistant(['mocktool.read'], {'max_tool_calls': 1})
storm_chat = conversation(storm_agent)
before = stats()
events = message(storm_chat, '__e2e_tool_storm__', 'agent-e2e-storm')
assert events[-1]['event_type'] == 'agent.failed' and events[-1]['payload']['code'] == 'tool_call_limit'
after = stats()
assert after['reads'] == before['reads'], (before, after)
print('Agent read tool, unauthorized tool, call limit, audit and SSE terminal: passed')
