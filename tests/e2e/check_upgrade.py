#!/usr/bin/env python3
"""Upgrade/rollback E2E: schema 14 -> 15, graceful shutdown, newer-schema refusal."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = []


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def compose(*args, capture=False, check=True, stdin=None):
    result = subprocess.run([*COMPOSE, *args], cwd=ROOT, check=False, text=True,
                            capture_output=capture, input=stdin)
    if check and result.returncode != 0:
        print(result.stdout or '', file=sys.stderr)
        print(result.stderr or '', file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, result.args,
                                            output=result.stdout, stderr=result.stderr)
    return result


def psql(sql, capture=True):
    return compose('exec', '-T', 'postgres', 'psql', '-U', 'uai', '-d', 'uai',
                   '-v', 'ON_ERROR_STOP=1', '-tAc', sql, capture=capture).stdout.strip()


def apply_migrations_through(version):
    for path in sorted((ROOT / 'apps/gateway/migrations').glob('*.sql')):
        number = int(path.name[:3])
        if number > version:
            break
        compose('exec', '-T', 'postgres', 'psql', '-U', 'uai', '-d', 'uai',
                '-v', 'ON_ERROR_STOP=1', stdin=path.read_text(), capture=True)


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


def sse(path, content, key):
    req = Request(BASE + path, data=json.dumps({'content': content}).encode(), headers={
        'Authorization': 'Bearer ' + KEY,
        'Content-Type': 'application/json',
        'Idempotency-Key': key,
    })
    with urlopen(req, timeout=60) as response:
        return response.headers, response.read().decode()


def events(stream):
    return [json.loads(line[5:].strip()) for line in stream.splitlines()
            if line.startswith('data: ')]


def wait_health(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if request('/v1/health', timeout=2)[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError('gateway did not become healthy')


def main():
    global COMPOSE, BASE, KEY
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args()
    project = 'uai-upgrade-' + str(os.getpid())
    tmp = Path(tempfile.mkdtemp(prefix='uai-upgrade-env-'))
    port, qdrant_port = free_port(), free_port()
    KEY = 'upgrade-admin-' + uuid.uuid4().hex
    env_file = tmp / 'env'
    env_file.write_text('\n'.join([
        'POSTGRES_PASSWORD=' + uuid.uuid4().hex,
        'INTERNAL_API_KEY=' + uuid.uuid4().hex,
        'ISOLATED_PLUGIN_TOKEN=' + uuid.uuid4().hex,
        'RUSTFS_ACCESS_KEY=' + uuid.uuid4().hex,
        'RUSTFS_SECRET_KEY=' + uuid.uuid4().hex,
        'UAI_API_KEY_SHA256=' + hashlib.sha256(KEY.encode()).hexdigest(),
        'MODEL_NAME=test',
        'MODEL_BASE_URL=http://mock-provider:9000/v1',
        'UAI_BIND_ADDRESS=127.0.0.1',
        f'UAI_PORT={port}',
        'UAI_RATE_LIMIT=10000',
        'UAI_RATE_LIMIT_PER_PRINCIPAL=10000',
        'UAI_WIDGET_ORIGINS=http://widget.e2e',
        'UAI_WIDGET_RATE_LIMIT=1000',
        'UAI_RETENTION_CONVERSATION_DAYS=0',
        'UAI_RETENTION_AUDIT_DAYS=0',
        'UAI_RETENTION_APPROVAL_DAYS=0',
        'UAI_RETENTION_CLEANUP_DAYS=0',
        'QDRANT_TEST_PORT=' + str(qdrant_port),
        '',
    ]))
    BASE = f'http://127.0.0.1:{port}'
    COMPOSE = ['docker', 'compose', '--env-file', str(env_file), '-p', project,
               '-f', 'compose.yaml', '-f', 'tests/e2e/compose.yaml',
               '--profile', 'worker']
    report = {'project': project}

    def cleanup():
        try:
            compose('--profile', 'worker', '--profile', 'rag', 'down', '-v',
                    capture=True, check=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    try:
        compose('build', 'gateway', 'runtime', 'worker', capture=True)
        compose('up', '-d', '--wait', '--wait-timeout', '180', 'postgres', capture=True)
        apply_migrations_through(14)
        assert psql("SELECT max(version) FROM schema_migrations") == '14'
        report['old_schema'] = 14
        compose('up', '-d', '--wait', '--wait-timeout', '180',
                'mock-provider', 'runtime', 'gateway', capture=True)
        wait_health()
        assert psql("SELECT max(version) FROM schema_migrations") == '15'
        report['new_schema'] = 15

        assistant = checked('/v1/assistants', method='POST',
                            body={'name': 'Upgrade assistant', 'model': 'test',
                                  'system_prompt': 'Helpful'})
        conversation = checked('/v1/conversations', method='POST',
                               body={'assistant_id': assistant['id']})['id']
        path = f'/v1/conversations/{conversation}/messages'
        _, stream = sse(path, 'Ciao upgrade', 'upgrade-seed')
        assert events(stream)[-1]['event_type'] == 'response.completed'
        report['seed_run'] = events(stream)[-1]['run_id']
        assert len(checked(f'/v1/conversations/{conversation}/messages')) == 2

        slow_conversation = checked('/v1/conversations', method='POST',
                                    body={'assistant_id': assistant['id']})['id']
        slow_path = f'/v1/conversations/{slow_conversation}/messages'
        slow_key = 'upgrade-graceful-' + uuid.uuid4().hex
        result = {}

        def slow_request():
            try:
                result['stream'] = sse(slow_path, '__e2e_slow__', slow_key)[1]
            except Exception as error:  # noqa: BLE001 - asserted below
                result['error'] = repr(error)

        thread = threading.Thread(target=slow_request)
        thread.start()
        deadline = time.time() + 15
        while time.time() < deadline:
            runs = checked('/v1/agent-runs')
            if any(run['conversation_id'] == slow_conversation and run['status'] == 'running'
                   for run in runs):
                break
            time.sleep(0.1)
        else:
            raise AssertionError('slow run did not start before graceful shutdown')
        compose('stop', 'gateway', capture=True)
        thread.join(timeout=30)
        assert not thread.is_alive(), 'graceful shutdown did not finish the in-flight client'
        assert 'error' not in result, result
        assert events(result['stream'])[-1]['event_type'] == 'response.completed', result
        compose('up', '-d', '--wait', '--wait-timeout', '90', 'gateway', capture=True)
        wait_health()
        _, replay = sse(slow_path, '__e2e_slow__', slow_key)
        assert replay == result['stream'], 'graceful-shutdown replay changed'
        report['graceful_shutdown'] = True

        compose('stop', 'gateway', capture=True)
        psql("INSERT INTO schema_migrations(version) VALUES (16)")
        result = compose('run', '--rm', '--no-deps', 'gateway',
                         capture=True, check=False)
        assert result.returncode != 0, 'newer database schema was accepted'
        report['newer_schema_refused'] = True
        psql("DELETE FROM schema_migrations WHERE version=16")
        compose('up', '-d', '--wait', '--wait-timeout', '90', 'gateway', capture=True)
        wait_health()
        _, replay = sse(path, 'Ciao upgrade', 'upgrade-seed')
        assert replay == stream, 'data/replay changed after schema rollback'
        assert len(checked(f'/v1/conversations/{conversation}/messages')) == 2
        report['data_preserved'] = True

        payload = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            Path(args.output).write_text(payload + '\n')
        print(payload)
        print('Upgrade 14->15, graceful shutdown, newer-schema refusal and data recovery: passed',
              file=sys.stderr)
    finally:
        cleanup()


if __name__ == '__main__':
    main()
