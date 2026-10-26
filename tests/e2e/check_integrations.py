"""Real gateway checks for widget tokens, CORS and the SDK-level boundaries."""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
ADMIN = os.environ['UAI_TEST_KEY']
ORIGIN = os.environ.get('UAI_TEST_WIDGET_ORIGIN', 'http://widget.e2e')
MODEL = os.environ.get('UAI_TEST_MODEL', 'test')


def request(path, *, method='GET', body=None, key=ADMIN, headers=None):
    request_headers = {'Authorization': 'Bearer ' + key}
    if body is not None:
        request_headers['Content-Type'] = 'application/json'
    if headers:
        request_headers.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data=data, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode(), dict(response.headers)
    except HTTPError as error:
        return error.code, error.read().decode(), dict(error.headers)


status, data, _ = request('/v1/assistants', method='POST', body={
    'name': 'Integrations widget', 'model': MODEL, 'system_prompt': 'Helpful',
})
assert status == 201, data
assistant = json.loads(data)['id']
status, data, _ = request('/v1/conversations', method='POST', body={'assistant_id': assistant})
assert status == 201, data
conversation = json.loads(data)['id']
status, data, _ = request('/v1/conversations', method='POST', body={'assistant_id': assistant})
assert status == 201, data
other_conversation = json.loads(data)['id']

status, data, _ = request('/v1/widget/tokens', method='POST', body={
    'assistant_id': assistant,
    'conversation_id': conversation,
    'subject': 'e2e-browser',
    'origin': ORIGIN,
    'expires_in_seconds': 600,
})
assert status == 201, data
minted = json.loads(data)
token = minted['token']
assert token.startswith('uai_widget_') and len(token) > 40, minted
assert minted['scopes'] == ['messages:read', 'messages:write'], minted
assert ADMIN not in data and 'key_digest' not in data, minted

status, data, _ = request('/v1/me', key=token)
assert status == 200, data
principal = json.loads(data)
assert principal['role'] == 'widget' and principal['scopes'] == ['messages:read', 'messages:write'], principal
assert request('/v1/credentials', key=token)[0] == 403
assert request('/v1/widget/tokens', method='POST', key=token, body={
    'assistant_id': assistant, 'conversation_id': conversation, 'origin': ORIGIN,
})[0] == 403

preflight_headers = {
    'Origin': ORIGIN,
    'Access-Control-Request-Method': 'POST',
    'Access-Control-Request-Headers': 'authorization, content-type, idempotency-key',
}
status, _, headers = request(f'/v1/conversations/{conversation}/messages', method='OPTIONS', headers=preflight_headers)
assert status == 204, status
assert headers.get('Access-Control-Allow-Origin') == ORIGIN, headers
assert 'Authorization' in headers.get('Access-Control-Allow-Headers', ''), headers
assert request(f'/v1/conversations/{conversation}/messages', method='OPTIONS', headers={
    'Origin': 'https://evil.example', 'Access-Control-Request-Method': 'POST',
})[0] == 403

status, data, _ = request(f'/v1/conversations/{conversation}/messages', key=token, headers={'Origin': ORIGIN})
assert status == 200, data
assert request(f'/v1/conversations/{other_conversation}/messages', key=token, headers={'Origin': ORIGIN})[0] == 403
assert request(f'/v1/conversations/{conversation}/messages', key=token, headers={'Origin': 'https://evil.example'})[0] == 403

status, stream, headers = request(
    f'/v1/conversations/{conversation}/messages',
    method='POST',
    key=token,
    headers={'Origin': ORIGIN, 'Idempotency-Key': 'widget-e2e-1'},
    body={'content': 'Ciao widget'},
)
assert status == 200, stream
assert headers.get('Content-Type', '').startswith('text/event-stream'), headers
events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
assert [event['event_type'] for event in events] == ['agent.started', 'response.delta', 'response.completed'], events
assert events[-1]['payload']['text'] == 'Risposta mock: Ciao widget', events[-1]
status, data, _ = request(f'/v1/conversations/{conversation}/messages', key=token, headers={'Origin': ORIGIN})
assert status == 200, data
assert json.loads(data) == [
    {'role': 'user', 'content': 'Ciao widget'},
    {'role': 'assistant', 'content': 'Risposta mock: Ciao widget'},
], data

status, data, _ = request(f"/v1/widget/tokens/{minted['id']}", method='DELETE')
assert status == 200, data
assert request(f'/v1/conversations/{conversation}/messages', key=token, headers={'Origin': ORIGIN})[0] == 401

print('E2E integrations/widget tokens: passed')
