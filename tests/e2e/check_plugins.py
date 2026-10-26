"""Runtime-only installed hello smoke. Public administration is a separate gate."""
import json
import os
import urllib.error
import urllib.request
from uuid import uuid4

BASE = 'http://127.0.0.1:8000/internal/v1'
KEY = os.environ['INTERNAL_API_KEY']


def send(path, body=None, *, method='GET', authorized=True):
    headers = {'Content-Type': 'application/json'}
    if authorized:
        headers['Authorization'] = 'Bearer ' + KEY
    request = urllib.request.Request(BASE + path,
        data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


path = '/plugins/org.uai.hello'
assert send('/plugins', authorized=False)[0] == 401
assert any(item['manifest']['id'] == 'org.uai.hello' for item in json.loads(send('/plugins')[1]))
assert send(path + '/activate', {'import_path': 'unapproved'}, method='POST')[0] == 409
assert send(path + '/activate', {}, method='POST')[0] == 204
try:
    for selected in (False, True):
        body = dict(run_id=str(uuid4()), correlation_id=str(uuid4()), model='test',
                    system_prompt='Helpful', messages=[{'role': 'user', 'content': 'Plugin test'}],
                    assistant=dict(id=str(uuid4()), version=1, name='Plugin test', model='test',
                                   system_prompt='Helpful', directives=['org.uai.hello.greeting'] if selected else []))
        status, text = send('/runs', body, method='POST')
        assert status == 200, status
        events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith('data: ')]
        assert events[-1]['event_type'] == 'response.completed', events[-1]
        assert events[-1]['payload']['text'] == 'Risposta mock: ' + ('Hello! ' if selected else '') + 'Plugin test'
finally:
    assert send(path + '/deactivate', method='POST')[0] == 204
assert send('/directives/validate', {'directives': ['org.uai.hello.greeting']}, method='POST')[0] == 422
print('Installed hello runtime activation, assistant selection and removal: passed')
