#!/usr/bin/env python3
"""Reproducible chat/SSE, ingestion and retrieval workload for M6-06.

The script targets an already-running E2E stack (the one created by
tests/e2e/run.sh) and never calls a cloud provider. It writes a JSON baseline
consumed by tests/performance/check_baseline.py and docs/capacity.md.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ.get('UAI_TEST_URL', '')
KEY = os.environ.get('UAI_TEST_KEY', '')


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
    status, response_headers, raw = request(path, method=method, body=body,
                                            headers=headers, timeout=timeout)
    assert status in (200, 201), (path, status, raw)
    return json.loads(raw) if raw else None


def multipart_upload(kb, filename, content):
    boundary = '----uai-perf-' + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="knowledge_base_id"\r\n\r\n{kb}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{filename}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: text/plain\r\n\r\n'
    ).encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    req = Request(BASE + '/v1/documents', data=body, method='POST', headers={
        'Authorization': 'Bearer ' + KEY,
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    })
    with urlopen(req, timeout=60) as response:
        assert response.status == 201, (response.status, response.read())
        return json.loads(response.read())


def wait_job(document_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _, raw = request(f'/v1/documents/{document_id}/job')
        if status == 200:
            job = json.loads(raw)
            if job['state'] in ('completed', 'failed', 'cancelled'):
                return job
        time.sleep(0.1)
    raise AssertionError(f'job timeout for {document_id}')


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def ms(seconds):
    return round(seconds * 1000.0, 2)


def sse_message(conversation, content, key, allow_cancelled=False):
    path = f'/v1/conversations/{conversation}/messages'
    req = Request(BASE + path, data=json.dumps({'content': content}).encode(), headers={
        'Authorization': 'Bearer ' + KEY,
        'Content-Type': 'application/json',
        'Idempotency-Key': key,
    })
    started = time.perf_counter()
    first_event = None
    events = []
    with urlopen(req, timeout=60) as response:
        assert response.status == 200, (response.status, response.read())
        headers = response.headers
        for raw_line in response:
            line = raw_line.decode()
            if not line.startswith('data:'):
                continue
            event = json.loads(line[5:].strip())
            if first_event is None:
                first_event = time.perf_counter() - started
            events.append(event)
        total = time.perf_counter() - started
    assert events, 'SSE stream had no events'
    terminal = events[-1]['event_type']
    if allow_cancelled:
        assert terminal in ('response.completed', 'agent.cancelled'), events[-1:]
    else:
        assert terminal == 'response.completed', events[-1:]
    return {
        'ttfb_ms': ms(first_event or total),
        'total_ms': ms(total),
        'run_id': headers.get('X-Run-ID'),
        'terminal': terminal,
        'citations': len(events[-1].get('payload', {}).get('citations') or []),
        'events': len(events),
    }


def create_assistant(name, kb=None):
    body = {'name': name, 'model': 'test', 'system_prompt': 'Helpful fixture prompt.'}
    if kb:
        body['knowledge_base_ids'] = [kb]
        body['directives'] = ['builtin.rag']
    return checked('/v1/assistants', method='POST', body=body)


def create_conversation(assistant_id):
    return checked('/v1/conversations', method='POST',
                   body={'assistant_id': assistant_id})['id']


def wait_index(kb_id, timeout=120):
    started = time.perf_counter()
    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _, raw = request(f'/v1/knowledge-bases/{kb_id}/versions')
        if status == 200:
            last = json.loads(raw)
            ready = [version for version in last
                     if version['state'] == 'active' and version['chunk_count'] > 0
                     and version.get('embedding') and version.get('collection_name')]
            if ready:
                return {
                    'seconds': round(time.perf_counter() - started, 3),
                    'chunk_count': ready[0]['chunk_count'],
                    'collection_name': ready[0]['collection_name'],
                }
        time.sleep(0.5)
    raise AssertionError(f'knowledge base index not ready: {last}')


def seed_knowledge_base(document_count):
    kb = checked('/v1/knowledge-bases', method='POST', body={
        'name': 'Performance fixture KB',
        'config': {'chunk_size': 1000, 'chunk_overlap': 200},
        'embedding': {'provider': 'ollama', 'model': 'test-embed',
                      'version': 'test-v1', 'dimension': 8},
    })
    jobs = []
    started = time.perf_counter()
    for index in range(document_count):
        text = (f'Performance fixture {index}. ' + 'retrieval provenance marker ' * 250).encode()
        upload_started = time.perf_counter()
        document = multipart_upload(kb['id'], f'perf-{index}.txt', text)
        jobs.append((document['id'], upload_started))
    completed = 0
    failed = 0
    latencies = []
    for document_id, upload_started in jobs:
        job = wait_job(document_id)
        if job['state'] == 'completed':
            completed += 1
            latencies.append(time.perf_counter() - upload_started)
        else:
            failed += 1
    current = checked(f'/v1/knowledge-bases/{kb["id"]}')
    status, _, raw = request(f'/v1/knowledge-bases/{kb["id"]}/versions', method='POST',
                             headers={'If-Match': f'"{current["revision"]}"'},
                             body={'config': {'chunk_size': 1000, 'chunk_overlap': 200},
                                   'embedding': {'provider': 'ollama', 'model': 'test-embed',
                                                 'version': 'test-v1', 'dimension': 8}})
    assert status == 201, (status, raw)
    return {
        'kb': kb['id'],
        'documents': document_count,
        'completed': completed,
        'failed': failed,
        'wall_seconds': round(time.perf_counter() - started, 3),
        'p50_ms': ms(percentile(latencies, 0.50)),
        'p95_ms': ms(percentile(latencies, 0.95)),
        'index': wait_index(kb['id']),
    }


def run_chat_workload(assistant_id, count, concurrency):
    conversations = [create_conversation(assistant_id) for _ in range(count)]
    keys = [f'perf-{uuid.uuid4().hex}' for _ in range(count)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        results = list(pool.map(lambda args: sse_message(args[0], 'Ciao performance', args[1]),
                                zip(conversations, keys)))
    wall = time.perf_counter() - started
    return {
        'requests': count,
        'completed': len(results),
        'concurrency': concurrency,
        'wall_seconds': round(wall, 3),
        'throughput_rps': round(count / wall, 3) if wall else 0.0,
        'p50_ms': ms(percentile([r['total_ms'] / 1000 for r in results], 0.50)),
        'p95_ms': ms(percentile([r['total_ms'] / 1000 for r in results], 0.95)),
        'ttfb_p95_ms': ms(percentile([r['ttfb_ms'] / 1000 for r in results], 0.95)),
        'citations': sum(r['citations'] for r in results),
    }


def run_slow_provider(assistant_id, count):
    conversations = [create_conversation(assistant_id) for _ in range(count)]
    keys = [f'slow-{uuid.uuid4().hex}' for _ in range(count)]
    results = {}
    errors = []
    lock = threading.Lock()

    def send(index):
        try:
            outcome = sse_message(conversations[index], '__e2e_slow__', keys[index],
                                  allow_cancelled=True)
            with lock:
                results[index] = outcome
        except Exception as error:  # noqa: BLE001 - reported in the baseline
            with lock:
                errors.append(repr(error))

    threads = [threading.Thread(target=send, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    run_id = None
    deadline = time.time() + 10
    while time.time() < deadline and run_id is None:
        status, _, raw = request('/v1/agent-runs')
        if status == 200:
            for run in json.loads(raw):
                if run['conversation_id'] in conversations and run['status'] == 'running':
                    run_id = run['id']
                    break
        time.sleep(0.1)
    if run_id is None:
        raise AssertionError('slow provider run did not become visible')
    time.sleep(1.0)
    started = time.perf_counter()
    health_status, _, health_raw = request('/v1/health', timeout=5)
    health_ms = ms(time.perf_counter() - started)
    cancel_status, _, cancel_raw = request(f'/v1/agent-runs/{run_id}/cancel', method='POST')
    cancelled = cancel_status == 200 and json.loads(cancel_raw)['status'] == 'cancelled'
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads), 'slow request did not terminate'
    assert health_status == 200, (health_status, health_raw)
    assert not errors, errors
    return {
        'requests': count,
        'health_status': health_status,
        'health_ms_during_load': health_ms,
        'cancel_accepted': cancelled,
        'completed': sum(1 for item in results.values()
                         if item['terminal'] == 'response.completed'),
        'cancelled': sum(1 for item in results.values()
                         if item['terminal'] == 'agent.cancelled'),
        'cancelled_run': run_id,
        'max_total_ms': max((item['total_ms'] for item in results.values()), default=0),
    }


def memory_mb(value):
    match = re.match(r'([0-9.]+)\s*([KMG]i?B)', value.strip())
    if not match:
        return 0.0
    amount = float(match.group(1))
    unit = match.group(2)
    factor = {'KiB': 1 / 1024, 'KB': 1 / 1000, 'MiB': 1, 'MB': 1,
              'GiB': 1024, 'GB': 1000}[unit]
    return round(amount * factor, 2)


def docker_resources(project):
    if not project:
        return {}
    try:
        names = subprocess.check_output(
            ['docker', 'ps', '--filter', f'label=com.docker.compose.project={project}',
             '--format', '{{.Names}}'], text=True, timeout=20).split()
        if not names:
            return {}
        output = subprocess.check_output(
            ['docker', 'stats', '--no-stream', '--format', '{{json .}}', *names],
            text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    resources = {}
    prefix = project + '-'
    for line in output.splitlines():
        row = json.loads(line)
        name = row['Name']
        service = name[len(prefix):] if name.startswith(prefix) else name
        service = service.rsplit('-', 1)[0]
        resources[service] = {
            'cpu_percent': float(row['CPUPerc'].rstrip('%')),
            'memory_mb': memory_mb(row['MemUsage'].split('/')[0].strip()),
        }
    return resources


def sample_peak(stop, project, peak):
    while not stop.is_set():
        for service, usage in docker_resources(project).items():
            current = peak.setdefault(service, {'cpu_percent': 0.0, 'memory_mb': 0.0})
            current['cpu_percent'] = max(current['cpu_percent'], usage['cpu_percent'])
            current['memory_mb'] = max(current['memory_mb'], usage['memory_mb'])
        stop.wait(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--documents', type=int, default=int(os.environ.get('UAI_PERF_DOCS', '4')))
    parser.add_argument('--chats', type=int, default=int(os.environ.get('UAI_PERF_CHATS', '8')))
    parser.add_argument('--retrieval', type=int, default=int(os.environ.get('UAI_PERF_RETRIEVAL', '4')))
    parser.add_argument('--slow', type=int, default=int(os.environ.get('UAI_PERF_SLOW', '2')))
    parser.add_argument('--concurrency', type=int, default=int(os.environ.get('UAI_PERF_CONCURRENCY', '2')))
    parser.add_argument('--project', default=os.environ.get('UAI_TEST_PROJECT', ''))
    parser.add_argument('--output')
    args = parser.parse_args()
    if not BASE or not KEY:
        parser.error('UAI_TEST_URL and UAI_TEST_KEY are required')
    if min(args.documents, args.chats, args.retrieval, args.slow, args.concurrency) < 1:
        parser.error('workload sizes must be positive')

    stop = threading.Event()
    peak = {}
    sampler = threading.Thread(target=sample_peak, args=(stop, args.project, peak), daemon=True)
    sampler.start()
    try:
        ingestion = seed_knowledge_base(args.documents)
        chat_assistant = create_assistant('Performance chat')
        rag_assistant = create_assistant('Performance retrieval', ingestion['kb'])
        chat = run_chat_workload(chat_assistant['id'], args.chats, args.concurrency)
        retrieval = run_chat_workload(rag_assistant['id'], args.retrieval, args.concurrency)
        assert retrieval['citations'] > 0, 'retrieval workload returned no citations'
        slow = run_slow_provider(chat_assistant['id'], args.slow)
    finally:
        stop.set()
        sampler.join(timeout=5)
    report = {
        'baseline_version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'host': platform.node(),
        'project': args.project,
        'workload': {'documents': args.documents, 'chats': args.chats,
                     'retrieval': args.retrieval, 'slow': args.slow,
                     'concurrency': args.concurrency},
        'ingestion': ingestion,
        'chat': chat,
        'retrieval': retrieval,
        'slow_provider': slow,
        'resources': docker_resources(args.project),
        'resources_peak': peak,
    }
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, 'w') as handle:
            handle.write(payload + '\n')
    print(payload)
    print('Performance workload: passed', file=sys.stderr)


if __name__ == '__main__':
    main()
