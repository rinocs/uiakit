"""Document upload, MIME/format validation, dedup and storage/job gate."""
import io
import json
import os
import secrets
import sys
import zipfile
from pathlib import Path
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


def credential():
    status, _, raw = request('/v1/credentials', {
        'role': 'operator',
        'scopes': ['documents:read', 'documents:write',
                   'knowledge-bases:read', 'knowledge-bases:write'],
    })
    assert status == 201, (status, raw)
    return json.loads(raw)['api_key']


def upload(kb_id, filename, mime, data, key, title=''):
    boundary = '----uai' + secrets.token_hex(12)
    chunks = []
    fields = [('knowledge_base_id', kb_id)]
    if title:
        fields.append(('title', title))
    for name, value in fields:
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                  f'Content-Type: {mime}\r\n\r\n'.encode())
    chunks.append(data)
    chunks.append(f'\r\n--{boundary}--\r\n'.encode())
    req = Request(BASE + '/v1/documents', data=b''.join(chunks),
                  headers={'Authorization': 'Bearer ' + key,
                           'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        with urlopen(req, timeout=60) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def docx(hostile=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        archive.writestr('word/document.xml',
                         '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                         '<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>')
        if hostile:
            archive.writestr('word/vbaProject.bin', 'macro')
    return buffer.getvalue()


owner, other = credential(), credential()
status, _, raw = request('/v1/knowledge-bases', {'name': 'Docs A'}, key=owner)
assert status == 201, (status, raw)
kb_a = json.loads(raw)
status, _, raw = request('/v1/knowledge-bases', {'name': 'Docs B'}, key=owner)
assert status == 201, (status, raw)
kb_b = json.loads(raw)

payload = b'Hello document'
status, headers, raw = upload(kb_a['id'], 'notes.txt', 'text/plain', payload, owner, 'Notes')
assert status == 201, (status, raw)
doc = json.loads(raw)
assert doc['ingestion_state'] == 'queued' and doc['size_bytes'] == len(payload)
assert doc['sha256'] and doc['blob_key'].startswith('documents/' + kb_a['id'] + '/')

status, headers, raw = upload(kb_a['id'], 'notes.txt', 'text/plain', payload, owner)
assert status == 200 and headers['X-Deduplicated'] == 'true', (status, raw)
assert json.loads(raw)['id'] == doc['id']
status, _, raw = upload(kb_b['id'], 'notes.txt', 'text/plain', payload, owner)
assert status == 201 and json.loads(raw)['id'] != doc['id'], (status, raw)

status, _, raw = request('/v1/documents?knowledge_base_id=' + kb_a['id'], key=owner)
assert status == 200 and doc['id'] in raw and kb_b['id'] not in raw
status, _, raw = request('/v1/documents/' + doc['id'], key=other)
assert status == 404, (status, raw)

pdf = Path('tests/fixtures/documents/sample.pdf').read_bytes()
status, _, raw = upload(kb_a['id'], 'bad.pdf', 'text/plain', pdf, owner)
assert status == 415, (status, raw)
status, _, raw = upload(kb_a['id'], 'ok.pdf', 'application/pdf', pdf, owner)
assert status == 201, (status, raw)
pdf_doc = json.loads(raw)
status, _, raw = upload(kb_a['id'], 'ok.docx',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        docx(), owner)
assert status == 201, (status, raw)
docx_doc = json.loads(raw)
status, _, raw = upload(kb_a['id'], 'cancel.txt', 'text/plain', b'cancel me', owner)
assert status == 201, (status, raw)
cancel_doc = json.loads(raw)
status, _, raw = request('/v1/documents/' + cancel_doc['id'] + '/job/cancel', method='POST', key=owner)
assert status == 200 and json.loads(raw)['state'] == 'cancelled', (status, raw)
status, _, raw = upload(kb_a['id'], 'bad.docx',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        docx(hostile=True), owner)
assert status == 415, (status, raw)

status, _, raw = request('/v1/knowledge-bases/' + kb_a['id'], method='DELETE', key=owner)
assert status == 428, (status, raw)
status, headers, raw = request('/v1/knowledge-bases/' + kb_a['id'], key=owner)
assert status == 200, (status, raw)
req = Request(BASE + '/v1/knowledge-bases/' + kb_a['id'], method='DELETE',
              headers={'Authorization': 'Bearer ' + owner, 'If-Match': headers['ETag']})
try:
    with urlopen(req, timeout=30) as response:
        status = response.status
except HTTPError as response:
    status, raw = response.code, response.read().decode()
assert status == 409, (status, raw)
status, _, raw = request('/v1/documents/' + doc['id'], method='DELETE', key=owner)
assert status == 204, (status, raw)
status, _, raw = request('/v1/documents/' + doc['id'], key=owner)
assert status == 404, (status, raw)
assert request('/v1/documents/' + pdf_doc['id'], key=owner)[0] == 200
assert request('/v1/documents/' + docx_doc['id'], key=owner)[0] == 200
if len(sys.argv) > 1:
    with open(sys.argv[1], 'w') as state:
        json.dump({'kb': kb_a['id'], 'pdf': pdf_doc['id'], 'docx': docx_doc['id'], 'cancelled': cancel_doc['id']}, state)
print('Document upload, MIME/format validation, dedup and job creation: passed')
