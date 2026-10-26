"""Real PostgreSQL auth/ownership acceptance checks; invoked by run.sh."""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
ADMIN = os.environ['UAI_TEST_KEY']
READ = ['assistants:read', 'conversations:read', 'messages:read']
OPERATE = READ + ['assistants:write', 'conversations:write', 'messages:write']


def request(path, body=None, key=ADMIN):
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def create(role, scopes, principal=None):
    body = {'role': role, 'scopes': scopes}
    if principal:
        body['principal_id'] = principal
    code, result = request('/v1/credentials', body)
    assert code == 201, code
    return result['credential'], result['api_key']


first, first_key = create('operator', OPERATE)
second, second_key = create('operator', OPERATE)
reader, reader_key = create('reader', READ, first['principal_id'])
code, assistant = request('/v1/assistants', {'name': 'Owned', 'model': 'test', 'system_prompt': ''}, first_key)
assert code == 201, code
code, conversation = request('/v1/conversations', {'assistant_id': assistant['id']}, first_key)
assert code == 201, code
path = f"/v1/conversations/{conversation['id']}/messages"
assert request('/v1/conversations', {'assistant_id': assistant['id']}, second_key)[0] == 404
assert request(path, key=second_key)[0] == 404
assert request('/v1/assistants/'+assistant['id'], key=second_key)[0] == 404
assert request('/v1/assistants/'+assistant['id']+'/versions', key=second_key)[0] == 404
assert request(path, key=reader_key) == (200, [])
assert request(path, {'content': 'Denied'}, reader_key)[0] == 403
assert request('/v1/credentials', key=first_key)[0] == 403
code, rows = request('/v1/assistants', key=second_key)
assert code == 200 and not any(a['id'] == assistant['id'] for a in rows)
code, rotated = request(f"/v1/credentials/{first['id']}/rotate", {})
assert code == 200, code
assert rotated['credential']['principal_id'] == first['principal_id']
assert request(path, key=first_key)[0] == 401
assert request(path, key=rotated['api_key'])[0] == 200
assert request(f"/v1/credentials/{first['id']}/revoke", {})[0] == 200
assert request(f"/v1/credentials/{first['id']}/revoke", {})[0] == 200
assert request(path, key=rotated['api_key'])[0] == 401
assert request('/v1/credentials', {'role': 'reader', 'scopes': ['credentials:write']})[0] == 422
expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
assert request('/v1/credentials', {'role': 'reader', 'scopes': READ, 'expires_at': expired})[0] == 422
code, listing = request('/v1/credentials')
assert code == 200
serialized = json.dumps(listing)
assert all(k not in serialized for k in [first_key, second_key, reader_key, rotated['api_key']])
assert 'key_digest' not in serialized
print('E2E credentials/scopes/ownership: passed')

expiry = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
code, temporary = request('/v1/credentials', {'role': 'reader', 'scopes': READ, 'expires_at': expiry})
assert code == 201
assert request('/v1/assistants', key=temporary['api_key'])[0] == 200
time.sleep(2.1)
assert request('/v1/assistants', key=temporary['api_key'])[0] == 401
print('E2E credential expiration: passed')
