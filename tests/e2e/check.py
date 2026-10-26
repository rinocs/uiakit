"""Full gateway → PostgreSQL → runtime → mock provider → SSE acceptance check."""
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
KEY = os.environ['UAI_TEST_KEY']
STATE = Path(sys.argv[2])


def request(path, body=None, *, key=KEY, idem=None):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    if idem:
        headers['Idempotency-Key'] = idem
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers)
    try:
        with urlopen(req, timeout=30) as res:
            return res.status, res.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def history(conversation):
    status, text = request(f'/v1/conversations/{conversation}/messages')
    assert status == 200, text
    messages = json.loads(text)
    assert messages == [{'role': 'user', 'content': 'Ciao'},
                        {'role': 'assistant', 'content': 'Risposta mock: Ciao'}], messages


if sys.argv[1] == 'initial':
    assert request('/v1/assistants', key='wrong')[0] == 401
    status, data = request('/v1/assistants', {'name': 'E2E', 'model': 'test', 'system_prompt': 'Helpful'})
    assert status == 201, data
    assistant = json.loads(data)['id']
    status, data = request('/v1/conversations', {'assistant_id': assistant})
    assert status == 201, data
    conversation = json.loads(data)['id']
    path = f'/v1/conversations/{conversation}/messages'
    status, stream = request(path, {'content': 'Ciao'}, idem='test-1')
    assert status == 200, stream
    events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
    assert [e['event_type'] for e in events] == ['agent.started', 'response.delta', 'response.completed'], events
    assert events[-1]['payload']['text'] == 'Risposta mock: Ciao'
    assert events[-1]['payload']['usage']['total_tokens'] == 9
    assert all(e['event_version'] == 1 and e['run_id'] == events[0]['run_id'] for e in events)
    status, replay = request(path, {'content': 'Ciao'}, idem='test-1')
    assert status == 200 and replay == stream, replay
    assert request(path, {'content': 'different'}, idem='test-1')[0] == 409
    history(conversation)
    STATE.write_text(json.dumps({'assistant': assistant, 'conversation': conversation, 'stream': stream}))
else:
    state = json.loads(STATE.read_text())
    history(state['conversation'])
    status, stream = request(f"/v1/conversations/{state['conversation']}/messages", {'content': 'Ciao'}, idem='test-1')
    assert status == 200 and stream == state['stream']
print('E2E ' + sys.argv[1] + ': passed')
