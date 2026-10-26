"""Public plugin desired state, assistant selection and real restart reconciliation."""
import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, KEY = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY']
MODE, STATE = sys.argv[1], Path(sys.argv[2])
PLUGIN = '/v1/plugins/org.uai.hello'


def request(path, body=None, method=None, extra=None):
    headers = {'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json', **(extra or {})}
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def message(conversation, selected):
    status, _, text = request('/v1/conversations/' + conversation + '/messages', {'content': 'Admin plugin test'},
                             extra={'Idempotency-Key': 'plugin-admin-' + MODE + str(selected)})
    assert status == 200, (status, text)
    events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith('data: ')]
    assert events[-1]['event_type'] == 'response.completed', events[-1]
    assert events[-1]['payload']['text'] == 'Risposta mock: ' + ('Hello! ' if selected else '') + 'Admin plugin test'


if MODE == 'initial':
    status, headers, raw = request('/v1/plugins')
    assert status == 200, (status, raw)
    initial = headers['ETag']
    assert request(PLUGIN, {'enabled': True, 'config': {}}, 'PUT')[0] == 428
    status, headers, raw = request(PLUGIN, {'enabled': True, 'config': {}}, 'PUT', {'If-Match': initial})
    assert status == 200 and json.loads(raw)['applied'], (status, raw)
    revision = headers['ETag']
    assert request(PLUGIN, {'enabled': False, 'config': {}}, 'PUT', {'If-Match': initial})[0] == 412
    assert request(PLUGIN, {'enabled': True, 'config': {'import_path': 'unapproved'}}, 'PUT', {'If-Match': revision})[0] == 422
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: request(PLUGIN, {'enabled': True, 'config': {}}, 'PUT',
                                                  {'If-Match': revision})[0], range(2)))
    assert sorted(replies) == [200, 412], replies
    status, headers, _ = request('/v1/plugins')
    assert status == 200
    revision = headers['ETag']
    state = {'revision': revision}
    for selected in (False, True):
        status, _, raw = request('/v1/assistants', {'name': 'Plugin admin', 'model': 'test',
            'system_prompt': 'Helpful', 'directives': ['org.uai.hello.greeting'] if selected else []})
        assert status == 201, (status, raw)
        status, _, raw = request('/v1/conversations', {'assistant_id': json.loads(raw)['id']})
        assert status == 201, (status, raw)
        state[str(selected)] = json.loads(raw)['id']
        message(state[str(selected)], selected)
    STATE.write_text(json.dumps(state))
else:
    state = json.loads(STATE.read_text())
    status, headers, raw = request('/v1/plugins')
    assert status == 200 and headers['ETag'] == state['revision'], (status, raw)
    catalog = json.loads(raw)
    assert catalog['applied'] and catalog['desired']['org.uai.hello']
    assert any(entry['manifest']['id'] == 'org.uai.hello' and entry['state'] == 'active' for entry in catalog['plugins'])
    message(state['True'], True)
    message(state['False'], False)
    if MODE == 'restarted':
        status, _, raw = request(PLUGIN, method='DELETE', extra={'If-Match': state['revision']})
        assert status == 200 and json.loads(raw)['applied'], (status, raw)
        status, _, raw = request('/v1/assistants', {'name': 'Removed plugin', 'model': 'test',
            'system_prompt': '', 'directives': ['org.uai.hello.greeting']})
        assert status == 422, (status, raw)
print('Public plugin administration and reconciliation (' + MODE + '): passed')
