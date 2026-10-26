"""Backup on a source installation, restore on an isolated destination, then query/replay/reindex."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ['docker', 'compose']


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def call(command: list[str], *, env=None, capture=False):
    return subprocess.run(command, cwd=ROOT, env=env, check=True,
                          text=True, capture_output=capture)


def compose(project: str, env_file: Path, *args: str, capture=False):
    return call([*COMPOSE, '--env-file', str(env_file), '-p', project,
                 '-f', 'compose.yaml', '-f', 'tests/e2e/compose.yaml', *args], capture=capture)


def up(project: str, env_file: Path):
    base = [*COMPOSE, '--env-file', str(env_file), '-p', project,
            '-f', 'compose.yaml', '-f', 'tests/e2e/compose.yaml',
            '--profile', 'worker', '--profile', 'rag', 'up', '-d', '--wait', '--wait-timeout', '240']
    for services in (['postgres', 'runtime', 'mock-provider', 'qdrant', 'worker'], ['gateway']):
        result = subprocess.run([*base, *services], cwd=ROOT, text=True, capture_output=True)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            try:
                compose(project, env_file, 'logs', '--no-color')
            except subprocess.CalledProcessError:
                pass
            raise SystemExit(f'compose up failed for {project}: {services}')


def down(project: str, env_file: Path):
    try:
        compose(project, env_file, '--profile', 'worker', '--profile', 'rag', 'down', '-v')
    except subprocess.CalledProcessError:
        pass


def request(base: str, path: str, *, method='GET', body=None, key=None, headers=None):
    req_headers = {}
    if key:
        req_headers['Authorization'] = 'Bearer ' + key
    if body is not None:
        req_headers['Content-Type'] = 'application/json'
    if headers:
        req_headers.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base + path, data=data, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=60) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode()


def multipart_upload(base: str, kb: str, key: str, filename: str, content: bytes):
    boundary = '----uai' + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="knowledge_base_id"\r\n\r\n{kb}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\nRestore source\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: text/plain\r\n\r\n'
    ).encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    req = Request(base + '/v1/documents', data=body, method='POST', headers={
        'Authorization': 'Bearer ' + key,
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    })
    with urlopen(req, timeout=60) as response:
        return response.status, json.loads(response.read())


def wait_for(check, timeout=120, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError('restore check timed out')


def seed(base: str, key: str):
    status, _, raw = request(base, '/v1/knowledge-bases', method='POST', key=key, body={'name': 'Restore KB'})
    assert status == 201, (status, raw)
    kb = json.loads(raw)
    status, document = multipart_upload(base, kb['id'], key, 'restore.txt', b'Restore provenance text.')
    assert status == 201, (status, document)
    document_id = document['id']
    def job_done():
        status, _, raw = request(base, f'/v1/documents/{document_id}/job', key=key)
        return status == 200 and json.loads(raw)['state'] == 'completed'
    wait_for(job_done)
    status, _, raw = request(base, f"/v1/knowledge-bases/{kb['id']}/versions", method='POST', key=key,
                             headers={'If-Match': f'"{kb["revision"]}"'},
                             body={'config': {'chunk_size': 1000, 'chunk_overlap': 200},
                                   'embedding': {'provider': 'ollama', 'model': 'test-embed', 'version': 'test-v1', 'dimension': 8}})
    assert status == 201, (status, raw)
    last_versions = ''
    for _ in range(90):
        status, _, last_versions = request(base, f"/v1/knowledge-bases/{kb['id']}/versions", key=key)
        if status == 200:
            versions = json.loads(last_versions)
            if any(version['state'] == 'active' and version['chunk_count'] > 0
                   and version.get('embedding') and version.get('collection_name')
                   for version in versions):
                break
        time.sleep(2)
    else:
        raise AssertionError(f'knowledge base version not ready: {last_versions}')
    status, _, raw = request(base, '/v1/assistants', method='POST', key=key, body={
        'name': 'Restore assistant', 'model': 'test', 'system_prompt': 'Answer from context.',
        'knowledge_base_ids': [kb['id']], 'directives': ['builtin.rag'],
    })
    assert status == 201, (status, raw)
    assistant = json.loads(raw)
    status, _, raw = request(base, '/v1/conversations', method='POST', key=key, body={'assistant_id': assistant['id']})
    assert status == 201, (status, raw)
    conversation = json.loads(raw)['id']
    status, _, stream = request(base, f'/v1/conversations/{conversation}/messages', method='POST', key=key,
                                headers={'Idempotency-Key': 'restore-seed'}, body={'content': 'What does it say?'})
    assert status == 200, (status, stream)
    events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
    assert events[-1]['event_type'] == 'response.completed', events
    assert events[-1]['payload'].get('citations'), events[-1]
    return {'kb': kb['id'], 'document': document_id, 'assistant': assistant['id'],
            'conversation': conversation, 'stream': stream, 'key': key}


def qdrant_points(qdrant: str) -> int:
    try:
        with urlopen(qdrant + '/collections', timeout=10) as response:
            collections = json.loads(response.read())['result']['collections']
    except urllib.error.HTTPError:
        return 0
    total = 0
    for collection in collections:
        name = collection['name']
        req = Request(qdrant + f'/collections/{name}/points/scroll',
                      data=json.dumps({'limit': 100, 'with_payload': False}).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=10) as response:
            total += len(json.loads(response.read())['result']['points'])
    return total


def main() -> int:
    project = 'uai-restore-' + str(os.getpid())
    source = project + '-src'
    destination = project + '-dst'
    key = 'restore-admin-' + uuid.uuid4().hex
    env_file = Path(tempfile.mkdtemp(prefix='uai-restore-env-')) / 'env'
    port = free_port()
    qdrant_port = free_port()
    env_file.write_text('\n'.join([
        'POSTGRES_PASSWORD=' + uuid.uuid4().hex,
        'INTERNAL_API_KEY=' + uuid.uuid4().hex,
        'ISOLATED_PLUGIN_TOKEN=' + uuid.uuid4().hex,
        'RUSTFS_ACCESS_KEY=' + uuid.uuid4().hex,
        'RUSTFS_SECRET_KEY=' + uuid.uuid4().hex,
        'UAI_API_KEY_SHA256=' + hashlib.sha256(key.encode()).hexdigest(),
        'MODEL_NAME=test',
        'MODEL_BASE_URL=http://mock-provider:9000/v1',
        'UAI_BIND_ADDRESS=127.0.0.1',
        f'UAI_PORT={port}',
        'UAI_RATE_LIMIT=10000',
        f'QDRANT_TEST_PORT={qdrant_port}',
        'UAI_RETENTION_CONVERSATION_DAYS=0',
        'UAI_RETENTION_AUDIT_DAYS=0',
        'UAI_RETENTION_APPROVAL_DAYS=0',
        'UAI_RETENTION_CLEANUP_DAYS=0',
        '',
    ]))
    base = f'http://127.0.0.1:{port}'
    qdrant = f'http://127.0.0.1:{qdrant_port}'
    backup = Path(tempfile.mkdtemp(prefix='uai-restore-backup-'))
    report = Path(tempfile.mkdtemp(prefix='uai-restore-report-')) / 'report.json'
    try:
        compose(source, env_file, '--profile', 'worker', '--profile', 'rag', 'build', 'runtime', 'gateway', 'worker')
        up(source, env_file)
        try:
            state = seed(base, key)
        except Exception:
            compose(source, env_file, 'logs', '--no-color', 'runtime', 'gateway', 'worker')
            raise
        status, _, raw = request(base, '/v1/health')
        assert status == 200, raw
        call(['deploy/backup.sh', '--env-file', str(env_file), '--project', source,
              '--output', str(backup), '--no-quiesce'])
        manifest = json.loads((backup / 'manifest.json').read_text())
        assert manifest['format'] == 'uai-backup-v1' and manifest['secrets_included'] is False
        assert manifest['timing']['rpo_upper_bound_seconds'] >= 0
        assert manifest['checksums']
        down(source, env_file)

        compose(destination, env_file, 'up', '-d', '--wait', '--wait-timeout', '120', 'postgres')
        call(['deploy/restore.sh', '--backup', str(backup), '--env-file', str(env_file),
              '--project', destination, '--reset-target', '--no-configs', '--report', str(report)])
        restored = json.loads(report.read_text())
        assert restored['checksums_verified'] is True
        assert restored['rto_seconds'] >= 0
        up(destination, env_file)
        assert qdrant_points(qdrant) == 0

        status, _, raw = request(base, f"/v1/conversations/{state['conversation']}/messages", key=key)
        assert status == 200, (status, raw)
        messages = json.loads(raw)
        assert [message['role'] for message in messages] == ['user', 'assistant'], messages
        status, _, replay = request(base, f"/v1/conversations/{state['conversation']}/messages",
                                    method='POST', key=key,
                                    headers={'Idempotency-Key': 'restore-seed'},
                                    body={'content': 'What does it say?'})
        assert status == 200 and replay == state['stream'], (status, replay[:200])
        assert qdrant_points(qdrant) == 0

        status, _, raw = request(base, f"/v1/knowledge-bases/{state['kb']}", key=key)
        assert status == 200, raw
        kb = json.loads(raw)
        status, _, raw = request(base, f"/v1/knowledge-bases/{state['kb']}/versions", key=key)
        versions = json.loads(raw)
        source_version = next(v for v in versions if v['state'] == 'active' and v.get('embedding'))
        body = {'config': source_version['config']}
        if source_version.get('embedding'):
            body['embedding'] = source_version['embedding']
        status, _, raw = request(base, f"/v1/knowledge-bases/{state['kb']}/versions", method='POST',
                                 key=key, headers={'If-Match': f'"{kb["revision"]}"'}, body=body)
        assert status == 201, (status, raw)
        def reindexed():
            status, _, raw = request(base, f"/v1/knowledge-bases/{state['kb']}", key=key)
            if status != 200:
                return False
            current = json.loads(raw)
            if current['active_version'] <= source_version['version']:
                return False
            status, _, raw = request(base, f"/v1/knowledge-bases/{state['kb']}/versions", key=key)
            if status != 200:
                return False
            versions = json.loads(raw)
            return any(v['version'] == current['active_version'] and v['state'] == 'active' and v['chunk_count'] > 0
                       for v in versions)
        wait_for(reindexed, timeout=180)
        assert qdrant_points(qdrant) > 0
        status, _, raw = request(base, '/v1/conversations', method='POST', key=key, body={'assistant_id': state['assistant']})
        assert status == 201, raw
        conversation = json.loads(raw)['id']
        status, _, stream = request(base, f'/v1/conversations/{conversation}/messages', method='POST', key=key,
                                    headers={'Idempotency-Key': 'restore-rag'}, body={'content': 'What does it say?'})
        assert status == 200, stream
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
        assert events[-1]['event_type'] == 'response.completed' and events[-1]['payload']['citations'], events[-1]

        incompatible = backup.parent / 'incompatible'
        if incompatible.exists():
            shutil.rmtree(incompatible)
        shutil.copytree(backup, incompatible)
        bad_manifest = json.loads((incompatible / 'manifest.json').read_text())
        bad_manifest['schema_version'] = 999
        (incompatible / 'manifest.json').write_text(json.dumps(bad_manifest, indent=2) + '\n')
        sums = []
        for name in ['postgres.dump', 'blobs.tar.gz', 'configs.tar.gz', 'manifest.json']:
            digest = hashlib.sha256((incompatible / name).read_bytes()).hexdigest()
            sums.append(f'{digest}  {name}')
        (incompatible / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
        failed = subprocess.run(['deploy/restore.sh', '--backup', str(incompatible),
                                 '--env-file', str(env_file), '--project', destination,
                                 '--reset-target', '--no-configs'], cwd=ROOT,
                                text=True, capture_output=True)
        assert failed.returncode != 0, failed
        status, _, raw = request(base, f"/v1/conversations/{state['conversation']}/messages", key=key)
        assert status == 200
        print('E2E backup/restore/query/replay/reindex: passed')
        return 0
    except Exception:
        try:
            compose(destination, env_file, 'logs', '--no-color', 'gateway', 'runtime')
        except subprocess.CalledProcessError:
            pass
        raise
    finally:
        down(destination, env_file)
        down(source, env_file)


if __name__ == '__main__':
    raise SystemExit(main())
