#!/usr/bin/env python3
"""Two simultaneous installations: separate ports, networks, volumes and keys."""
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
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run(command, *, cwd=ROOT, capture=False, check=True):
    return subprocess.run(command, cwd=cwd, check=check, text=True, capture_output=capture)


class Instance:
    def __init__(self, name):
        self.name = name
        self.project = f'uai-two-{name}-{os.getpid()}'
        self.tmp = Path(tempfile.mkdtemp(prefix=f'uai-two-{name}-'))
        self.port = free_port()
        self.key = 'two-admin-' + uuid.uuid4().hex
        self.env_file = self.tmp / 'env'
        self.env_file.write_text('\n'.join([
            'POSTGRES_PASSWORD=' + uuid.uuid4().hex,
            'INTERNAL_API_KEY=' + uuid.uuid4().hex,
            'ISOLATED_PLUGIN_TOKEN=' + uuid.uuid4().hex,
            'RUSTFS_ACCESS_KEY=' + uuid.uuid4().hex,
            'RUSTFS_SECRET_KEY=' + uuid.uuid4().hex,
            'UAI_API_KEY_SHA256=' + hashlib.sha256(self.key.encode()).hexdigest(),
            'MODEL_NAME=test',
            'MODEL_BASE_URL=http://mock-provider:9000/v1',
            'UAI_BIND_ADDRESS=127.0.0.1',
            f'UAI_PORT={self.port}',
            'UAI_RATE_LIMIT=10000',
            'UAI_RATE_LIMIT_PER_PRINCIPAL=10000',
            'UAI_WIDGET_ORIGINS=http://widget.e2e',
            'UAI_WIDGET_RATE_LIMIT=1000',
            'UAI_RETENTION_CONVERSATION_DAYS=0',
            'UAI_RETENTION_AUDIT_DAYS=0',
            'UAI_RETENTION_APPROVAL_DAYS=0',
            'UAI_RETENTION_CLEANUP_DAYS=0',
            'QDRANT_TEST_PORT=' + str(free_port()),
            '',
        ]))
        self.base = f'http://127.0.0.1:{self.port}'
        self.compose = ['docker', 'compose', '--env-file', str(self.env_file),
                        '-p', self.project, '-f', 'compose.yaml',
                        '-f', 'tests/e2e/compose.yaml']

    def compose_run(self, *args, capture=False, check=True):
        return run([*self.compose, *args], capture=capture, check=check)

    def request(self, path, *, method=None, body=None, key=None, headers=None, timeout=30):
        merged = {'Authorization': 'Bearer ' + (key or self.key)}
        if body is not None:
            merged['Content-Type'] = 'application/json'
        if headers:
            merged.update(headers)
        req = Request(self.base + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers=merged, method=method)
        try:
            with urlopen(req, timeout=timeout) as response:
                return response.status, response.read().decode()
        except HTTPError as response:
            return response.code, response.read().decode()

    def wait_health(self, timeout=90):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.request('/v1/health', timeout=2)[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        raise AssertionError(f'{self.name}: gateway did not become healthy')

    def create_assistant(self, name):
        status, raw = self.request('/v1/assistants', method='POST',
                                   body={'name': name, 'model': 'test',
                                         'system_prompt': 'Helpful'})
        assert status == 201, (status, raw)
        return json.loads(raw)['id']

    def assistant_names(self):
        status, raw = self.request('/v1/assistants')
        assert status == 200, (status, raw)
        return {assistant['name'] for assistant in json.loads(raw)}

    def chat(self, assistant_id):
        status, raw = self.request('/v1/conversations', method='POST',
                                   body={'assistant_id': assistant_id})
        assert status == 201, (status, raw)
        conversation = json.loads(raw)['id']
        status, raw = self.request(f'/v1/conversations/{conversation}/messages',
                                   method='POST', body={'content': 'Ciao due istanze'},
                                   headers={'Idempotency-Key': 'two-' + uuid.uuid4().hex})
        assert status == 200, (status, raw)
        events = [json.loads(line[5:].strip()) for line in raw.splitlines()
                  if line.startswith('data: ')]
        assert events[-1]['event_type'] == 'response.completed', events[-1]

    def volumes(self):
        output = run(['docker', 'volume', 'ls', '--filter',
                      f'label=com.docker.compose.project={self.project}',
                      '--format', '{{.Name}}'], capture=True).stdout
        return set(output.split())

    def services(self):
        output = run(['docker', 'ps', '--filter',
                      f'label=com.docker.compose.project={self.project}',
                      '--format', '{{.Label "com.docker.compose.service"}}'],
                     capture=True).stdout
        return set(output.split())

    def down(self):
        try:
            self.compose_run('--profile', 'worker', '--profile', 'rag', 'down', '-v',
                             capture=True, check=False)
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args()
    first, second = Instance('a'), Instance('b')
    try:
        first.compose_run('build', 'gateway', 'runtime', capture=True)
        for instance in (first, second):
            instance.compose_run('up', '-d', '--wait', '--wait-timeout', '180',
                                 'postgres', 'mock-provider', 'runtime', 'gateway',
                                 capture=True)
            instance.wait_health()
        services_a, services_b = first.services(), second.services()
        for optional in ('qdrant', 'worker', 'ollama', 'console'):
            assert optional not in services_a and optional not in services_b, \
                (optional, services_a, services_b)
        assert first.volumes() and second.volumes()
        assert first.volumes().isdisjoint(second.volumes()), 'volumes were shared'
        assert first.project != second.project

        assistant_a = first.create_assistant('Only A')
        assert first.assistant_names() == {'Only A'}, first.assistant_names()
        assert second.assistant_names() == set(), second.assistant_names()
        status, _ = second.request('/v1/assistants', key=first.key)
        assert status == 401, status
        assistant_b = second.create_assistant('Only B')
        assert second.assistant_names() == {'Only B'}, second.assistant_names()
        assert first.assistant_names() == {'Only A'}, first.assistant_names()
        first.chat(assistant_a)
        second.chat(assistant_b)

        first.compose_run('stop', 'gateway', capture=True)
        second.wait_health()
        assert second.assistant_names() == {'Only B'}
        first.compose_run('up', '-d', '--wait', '--wait-timeout', '90', 'gateway',
                          capture=True)
        first.wait_health()
        assert first.assistant_names() == {'Only A'}

        report = {
            'projects': [first.project, second.project],
            'ports': [first.port, second.port],
            'services': [sorted(services_a), sorted(services_b)],
            'volumes': [sorted(first.volumes()), sorted(second.volumes())],
            'core_only': True,
            'credentials_isolated': True,
            'data_isolated': True,
        }
        payload = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            Path(args.output).write_text(payload + '\n')
        print(payload)
        print('Two simultaneous core installations with isolated state: passed',
              file=sys.stderr)
    finally:
        first.down()
        second.down()


if __name__ == '__main__':
    main()
