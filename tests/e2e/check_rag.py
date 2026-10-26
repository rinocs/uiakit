"""E2E upload→retrieval→answer→verifiable citations via the public API."""
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, ADMIN, STATE = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY'], sys.argv[1]


def request(path, body=None, method=None, key=ADMIN, extra=None):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', **(extra or {})}
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


state = json.load(open(STATE))
kb, docx = state['kb'], state['docx']
status, _, raw = request('/v1/assistants', {
    'name': 'RAG E2E', 'model': 'test', 'system_prompt': 'Answer only from provided context.',
    'knowledge_base_ids': [kb], 'directives': ['builtin.rag'],
})
assert status == 201, (status, raw)
assistant = json.loads(raw)
assert assistant['knowledge_base_ids'] == [kb] and assistant['directives'] == ['builtin.rag']
status, _, raw = request('/v1/conversations', {'assistant_id': assistant['id']})
assert status == 201, (status, raw)
conversation = json.loads(raw)['id']
status, _, raw = request('/v1/conversations/' + conversation + '/messages',
                         {'content': 'What does the document say?'}, extra={'Idempotency-Key': 'rag-e2e'})
assert status == 200, (status, raw)
frames = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ')]
assert frames[-1]['event_type'] == 'response.completed', frames[-1]
payload = frames[-1]['payload']
assert '[C1]' in payload['text'] and payload['citations'], payload
assert payload['citations'][0]['citation_id'] == 'C1'
status, _, raw = request('/v1/knowledge-bases/' + kb + '/export')
assert status == 200, (status, raw)
export = json.loads(raw)
chunks = {chunk['chunk_id']: chunk for chunk in export['chunks']}
for citation in payload['citations']:
    assert citation['chunk_id'] in chunks
    chunk = chunks[citation['chunk_id']]
    assert citation['document_id'] == chunk['document_id']
    assert citation['document_version'] == chunk['document_version']
    assert citation['page'] == chunk['page']
    assert citation['start'] == chunk['start'] and citation['end'] == chunk['end']
    assert citation['knowledge_base_id'] == kb
    assert citation['document_id'] in {doc['id'] for doc in export['documents']}
# The assistant version remains the operator's; retrieval never changes prompt/policy.
assert assistant['system_prompt'] == 'Answer only from provided context.'
assert assistant['knowledge_base_ids'] == [kb]
print('RAG retrieval, answer and verifiable citations: passed')
