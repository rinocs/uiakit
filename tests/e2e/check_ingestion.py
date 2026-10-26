"""End-to-end reindex, atomic switch, export and vector cleanup with Qdrant."""
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, ADMIN, STATE = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY'], sys.argv[1]
QDRANT = os.environ['UAI_QDRANT_TEST_URL'].rstrip('/')


def request(path, body=None, method=None, extra=None):
    headers = {'Authorization': 'Bearer ' + ADMIN, 'Content-Type': 'application/json', **(extra or {})}
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def qdrant(path, body=None):
    req = Request(QDRANT + path, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def scroll(collection, document_id=None):
    body = {'limit': 100, 'with_payload': True}
    if document_id:
        body['filter'] = {'must': [{'key': 'document_id', 'match': {'value': document_id}}]}
    result = qdrant('/collections/' + collection + '/points/scroll', body)['result']
    return result['points']


def wait(predicate, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(1)
    raise AssertionError('timeout')


state = json.load(open(STATE))
kb_id, pdf_id, docx_id = state['kb'], state['pdf'], state['docx']
status, headers, raw = request('/v1/knowledge-bases/' + kb_id)
assert status == 200, (status, raw)
etag = headers['ETag']
status, headers, raw = request('/v1/knowledge-bases/' + kb_id + '/versions', {
    'config': {'chunk_size': 1000, 'chunk_overlap': 200},
    'embedding': {'provider': 'ollama', 'model': 'test-embed', 'version': 'test-v1', 'dimension': 8},
}, 'POST', {'If-Match': etag})
assert status == 201, (status, raw)
new_version = json.loads(raw)['version']
assert new_version == 2


def active_version():
    status, _, raw = request('/v1/knowledge-bases/' + kb_id)
    if status == 200 and json.loads(raw)['active_version'] == new_version:
        return json.loads(raw)
    return None


kb = wait(active_version)
status, _, raw = request('/v1/knowledge-bases/' + kb_id + '/versions')
versions = json.loads(raw)
version = next(v for v in versions if v['version'] == new_version)
assert version['state'] == 'active' and version['chunk_count'] > 0
assert version['collection_name'] and version['embedding']['dimension'] == 8
collection = version['collection_name']

points = wait(lambda: scroll(collection) or None)
assert len(points) == version['chunk_count'], (len(points), version['chunk_count'])
document_ids = {point['payload']['document_id'] for point in points}
assert {pdf_id, docx_id} <= document_ids

status, _, raw = request('/v1/knowledge-bases/' + kb_id + '/export')
assert status == 200, (status, raw)
export = json.loads(raw)
assert export['knowledge_base']['active_version'] == new_version
assert export['versions'][-1]['embedding']['model'] == 'test-embed'
assert {doc['id'] for doc in export['documents']} >= {pdf_id, docx_id}
assert export['chunks'] and 'blob_key' not in raw and 'secret' not in raw.lower()

status, _, raw = request('/v1/documents/' + pdf_id, method='DELETE')
assert status == 204, (status, raw)
wait(lambda: not scroll(collection, document_id=pdf_id), timeout=60)
status, _, raw = request('/v1/knowledge-bases/' + kb_id + '/export')
export = json.loads(raw)
assert pdf_id not in {doc['id'] for doc in export['documents']}
assert pdf_id not in {chunk['document_id'] for chunk in export['chunks']}
print('Ingestion reindex, atomic switch, export and vector cleanup: passed')
