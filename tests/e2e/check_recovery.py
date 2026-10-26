#!/usr/bin/env python3
"""Crash recovery E2E: gateway interrupted run + worker lease reclamation.

Run from tests/e2e/run.sh, which owns the isolated Compose project. The script
uses the public API plus Docker Compose/PostgreSQL only for fault injection.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ.get('UAI_TEST_URL', '')
KEY = os.environ.get('UAI_TEST_KEY', '')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMPOSE = []


def compose(*args, capture=False):
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, check=True, text=True,
                          capture_output=capture)


def psql(sql):
    return compose('exec', '-T', 'postgres', 'psql', '-U', 'uai', '-d', 'uai',
                   '-tAc', sql, capture=True).stdout.strip()


def request(path, *, method=None, body=None, headers=None, timeout=60):
    merged = {'Authorization': 'Bearer ' + KEY}
    if body is not None:
        merged['Content-Type'] = 'application/json'
    if headers:
        merged.update(headers)
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=merged, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, response.headers, response.read().decode()
    except HTTPError as response:
        return response.code, response.headers, response.read().decode()


def checked(path, *, method=None, body=None, headers=None, timeout=60):
    status, _, raw = request(path, method=method, body=body, headers=headers, timeout=timeout)
    assert status in (200, 201), (path, status, raw)
    return json.loads(raw) if raw else None


def wait_health(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _, _ = request('/v1/health', timeout=2)
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError('gateway did not become healthy after restart')


def sse(path, content, key):
    req = Request(BASE + path, data=json.dumps({'content': content}).encode(), headers={
        'Authorization': 'Bearer ' + KEY,
        'Content-Type': 'application/json',
        'Idempotency-Key': key,
    })
    with urlopen(req, timeout=60) as response:
        return response.status, response.headers, response.read().decode()


def events(stream):
    return [json.loads(line[5:].strip()) for line in stream.splitlines()
            if line.startswith('data: ')]


def gateway_crash():
    assistant = checked('/v1/assistants', method='POST',
                        body={'name': 'Recovery gateway', 'model': 'test',
                              'system_prompt': 'Helpful'})
    conversation = checked('/v1/conversations', method='POST',
                           body={'assistant_id': assistant['id']})['id']
    path = f'/v1/conversations/{conversation}/messages'
    key = 'recovery-gateway-' + uuid.uuid4().hex
    result = {}

    def send():
        try:
            result['stream'] = sse(path, '__e2e_slow__', key)[2]
        except Exception as error:  # noqa: BLE001 - expected on SIGKILL
            result['error'] = repr(error)

    thread = threading.Thread(target=send)
    thread.start()
    run = None
    deadline = time.time() + 20
    while time.time() < deadline and run is None:
        status, _, raw = request('/v1/agent-runs')
        if status == 200:
            for candidate in json.loads(raw):
                if candidate['conversation_id'] == conversation and candidate['status'] == 'running':
                    run = candidate
                    break
        time.sleep(0.1)
    assert run, 'running agent run not visible before crash'

    compose('kill', 'gateway')
    thread.join(timeout=20)
    assert not thread.is_alive(), 'client connection survived gateway SIGKILL'
    compose('up', '-d', '--wait', '--wait-timeout', '90', 'gateway')
    wait_health()

    status, _, raw = request('/v1/agent-runs/' + run['id'])
    assert status == 200 and json.loads(raw)['status'] == 'failed', (status, raw)
    status, _, replay = sse(path, '__e2e_slow__', key)
    assert status == 200, (status, replay)
    frames = events(replay)
    assert frames and frames[-1]['event_type'] == 'agent.failed', frames
    assert frames[-1]['payload']['code'] == 'gateway_restarted', frames[-1]
    correlation = psql(f"SELECT correlation_id FROM agent_runs WHERE id='{run['id']}'")
    assert frames[-1]['correlation_id'] == correlation, (frames[-1], correlation)
    assert frames[-1]['run_id'] == run['id'], frames[-1]

    status, _, stream = sse(path, 'Ciao dopo il crash', 'recovery-after-' + uuid.uuid4().hex)
    assert status == 200 and events(stream)[-1]['event_type'] == 'response.completed', stream[-500:]
    return {'run': run['id'], 'correlation': correlation}


def worker_crash():
    kb = checked('/v1/knowledge-bases', method='POST', body={'name': 'Recovery worker KB'})
    text = (b'recovery lease marker ' * 100000)[:1_500_000]
    boundary = '----uai-recovery-' + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="knowledge_base_id"\r\n\r\n{kb["id"]}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\nrecovery.txt\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="recovery.txt"\r\n'
        f'Content-Type: text/plain\r\n\r\n'
    ).encode() + text + f'\r\n--{boundary}--\r\n'.encode()
    req = Request(BASE + '/v1/documents', data=body, method='POST', headers={
        'Authorization': 'Bearer ' + KEY,
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    })
    with urlopen(req, timeout=60) as response:
        assert response.status == 201, (response.status, response.read())
        document = json.loads(response.read())
    document_id = document['id']

    def state():
        status, _, raw = request(f'/v1/documents/{document_id}/job')
        return json.loads(raw)['state'] if status == 200 else None

    killed = False
    deadline = time.time() + 20
    while time.time() < deadline:
        current = state()
        if current == 'running':
            compose('kill', 'worker')
            killed = True
            break
        if current in ('completed', 'failed', 'cancelled'):
            break
        time.sleep(0.02)

    # Deterministically leave a claim from a dead worker, then let the lease expire.
    psql(f"""UPDATE document_jobs SET state='running',attempts=1,lease_owner='dead-worker',
             lease_until=now()-interval '1 second',error_code='simulated_crash',updated_at=now()
             WHERE document_id='{document_id}'""")
    psql(f"DELETE FROM document_chunks WHERE document_id='{document_id}'")
    compose('start', 'worker')
    deadline = time.time() + 90
    last_state = None
    while time.time() < deadline:
        last_state = state()
        if last_state == 'completed':
            break
        time.sleep(0.2)
    else:
        raise AssertionError(f'worker did not reclaim the expired lease (state={last_state})')
    total, distinct = psql(
        f"SELECT count(*),count(DISTINCT chunk_id) FROM document_chunks WHERE document_id='{document_id}'"
    ).split('|')
    assert int(total) > 0 and total == distinct, (total, distinct)
    attempts = int(psql(f"SELECT attempts FROM document_jobs WHERE document_id='{document_id}'"))
    assert attempts >= 2, attempts
    return {'document': document_id, 'chunks': int(total), 'attempts': attempts,
            'worker_killed': killed}


def main():
    global COMPOSE
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default=os.environ.get('UAI_TEST_PROJECT', ''))
    parser.add_argument('--env-file', default=os.environ.get('UAI_TEST_ENVFILE', ''))
    parser.add_argument('--output')
    args = parser.parse_args()
    if not BASE or not KEY:
        parser.error('UAI_TEST_URL and UAI_TEST_KEY are required')
    if not args.project or not args.env_file:
        parser.error('--project and --env-file are required')
    COMPOSE = ['docker', 'compose', '--env-file', args.env_file, '-p', args.project,
               '-f', 'compose.yaml', '-f', 'tests/e2e/compose.yaml']
    try:
        report = {'gateway_crash': gateway_crash(), 'worker_crash': worker_crash()}
    finally:
        # Leave the stack usable for the following performance workload.
        try:
            compose('start', 'gateway', 'worker', capture=True)
        except subprocess.CalledProcessError:
            pass
        try:
            wait_health(30)
        except AssertionError:
            pass
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, 'w') as handle:
            handle.write(payload + '\n')
    print(payload)
    print('Gateway and worker crash recovery: passed', file=sys.stderr)


if __name__ == '__main__':
    main()
