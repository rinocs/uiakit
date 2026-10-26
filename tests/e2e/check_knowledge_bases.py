"""Knowledge base CRUD, versioning, ownership and assistant association gate."""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, ADMIN = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY']


def request(path, body=None, method=None, key=ADMIN):
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                  method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def mutate(path, body, method, etag, key):
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                           'If-Match': etag}, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def make_credential():
    status, _, raw = request('/v1/credentials', {
        'role': 'operator',
        'scopes': ['knowledge-bases:read', 'knowledge-bases:write',
                   'assistants:read', 'assistants:write',
                   'conversations:read', 'conversations:write',
                   'messages:read', 'messages:write'],
    })
    assert status == 201, (status, raw)
    return json.loads(raw)['api_key']


owner, other = make_credential(), make_credential()

status, headers, raw = request('/v1/knowledge-bases', {
    'name': 'E2E KB', 'description': 'Owned corpus',
    'config': {'chunk_size': 400, 'chunk_overlap': 40},
}, key=owner)
assert status == 201 and headers['ETag'] == '"1"', (status, raw)
kb = json.loads(raw)
assert kb['active_version'] == 1 and kb['revision'] == 1
path = '/v1/knowledge-bases/' + kb['id']

status, _, raw = request(path + '/versions', key=owner)
versions = json.loads(raw)
assert status == 200 and len(versions) == 1 and versions[0]['state'] == 'active'
assert versions[0]['config'] == {'chunk_size': 400, 'chunk_overlap': 40}

status, _, raw = mutate(path + '/versions',
                        {'config': {'chunk_size': 500, 'chunk_overlap': 50}},
                        'POST', '"1"', owner)
assert status == 201 and '"reindexing"' in raw, (status, raw)
status, headers, raw = request(path, key=owner)
assert status == 200 and headers['ETag'] == '"2"' and json.loads(raw)['active_version'] == 1
status, _, raw = mutate(path + '/versions',
                        {'config': {'chunk_size': 600, 'chunk_overlap': 60}},
                        'POST', '"2"', owner)
assert status == 409, (status, raw)
status, _, raw = request(path + '/versions', key=owner)
assert status == 200 and len(json.loads(raw)) == 2

status, headers, raw = request('/v1/assistants', {
    'name': 'KB assistant', 'model': 'test', 'system_prompt': 'Helpful',
    'knowledge_base_ids': [kb['id']],
}, key=owner)
assert status == 201 and json.loads(raw)['knowledge_base_ids'] == [kb['id']], (status, raw)
assistant = json.loads(raw)
status, _, raw = request('/v1/conversations', {'assistant_id': assistant['id']}, key=owner)
assert status == 201, (status, raw)
conversation = json.loads(raw)['id']
req = Request(BASE + '/v1/conversations/' + conversation + '/messages',
              data=json.dumps({'content': 'KB context'}).encode(),
              headers={'Authorization': 'Bearer ' + owner, 'Content-Type': 'application/json',
                       'Idempotency-Key': 'kb-association'})
with urlopen(req, timeout=30) as response:
    text = response.read().decode()
assert 'response.completed' in text and 'KB context' in text

assert request(path, key=other)[0] == 404
status, _, raw = request('/v1/knowledge-bases', key=other)
assert status == 200 and kb['id'] not in raw
status, _, raw = request('/v1/assistants', {
    'name': 'Foreign', 'model': 'test', 'system_prompt': '',
    'knowledge_base_ids': [kb['id']],
}, key=other)
assert status == 422, (status, raw)

status, _, raw = request('/v1/knowledge-bases', {'name': 'Other KB'}, key=other)
assert status == 201, (status, raw)
other_kb = json.loads(raw)
status, _, raw = request('/v1/assistants', {
    'name': 'Foreign two', 'model': 'test', 'system_prompt': '',
    'knowledge_base_ids': [other_kb['id']],
}, key=owner)
assert status == 422, (status, raw)

status, _, raw = mutate(path, None, 'DELETE', '"2"', owner)
assert status == 409, (status, raw)
status, _, raw = mutate('/v1/assistants/' + assistant['id'],
                        {'knowledge_base_ids': []}, 'PATCH', '"1"', owner)
assert status == 200 and json.loads(raw)['knowledge_base_ids'] == [], (status, raw)
status, _, raw = mutate(path, None, 'DELETE', '"2"', owner)
assert status == 204, (status, raw)
assert request(path, key=owner)[0] == 404
print('Knowledge base CRUD, versions, ownership and assistant association: passed')
