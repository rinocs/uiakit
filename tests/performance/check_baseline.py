#!/usr/bin/env python3
"""Validate a performance report and optionally compare it with a baseline."""
from __future__ import annotations

import argparse
import json
import sys


def fail(message):
    raise SystemExit('performance check failed: ' + message)


def compare(current, baseline):
    checks = [
        ('ingestion p95', current['ingestion']['p95_ms'],
         max(baseline['ingestion']['p95_ms'] * 2, baseline['ingestion']['p95_ms'] + 5000)),
        ('chat p95', current['chat']['p95_ms'],
         max(baseline['chat']['p95_ms'] * 2, baseline['chat']['p95_ms'] + 2000)),
        ('retrieval p95', current['retrieval']['p95_ms'],
         max(baseline['retrieval']['p95_ms'] * 2, baseline['retrieval']['p95_ms'] + 2000)),
    ]
    for name, value, limit in checks:
        if value > limit:
            fail(f'{name} {value}ms exceeds comparison limit {limit}ms')
    if current['chat']['throughput_rps'] < baseline['chat']['throughput_rps'] * 0.5:
        fail('chat throughput dropped below 50% of baseline')
    if current['retrieval']['citations'] == 0:
        fail('retrieval returned no citations')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report')
    parser.add_argument('--baseline')
    args = parser.parse_args()
    with open(args.report) as handle:
        report = json.load(handle)

    ingestion = report['ingestion']
    if ingestion['failed'] or ingestion['completed'] != ingestion['documents']:
        fail(f"ingestion completed {ingestion['completed']}/{ingestion['documents']}, "
             f"failed {ingestion['failed']}")
    if ingestion['p95_ms'] > 60000:
        fail(f"ingestion p95 {ingestion['p95_ms']}ms exceeds 60s")
    if not ingestion.get('index') or ingestion['index']['chunk_count'] <= 0:
        fail('knowledge base index was not ready')

    chat = report['chat']
    if chat['completed'] != chat['requests']:
        fail(f"chat completed {chat['completed']}/{chat['requests']}")
    if chat['p95_ms'] > 15000:
        fail(f"chat p95 {chat['p95_ms']}ms exceeds 15s")
    if chat['throughput_rps'] <= 0.1:
        fail(f"chat throughput {chat['throughput_rps']} rps is too low")

    retrieval = report['retrieval']
    if retrieval['completed'] != retrieval['requests']:
        fail(f"retrieval completed {retrieval['completed']}/{retrieval['requests']}")
    if retrieval['citations'] == 0:
        fail('retrieval workload returned no citations')
    if retrieval['p95_ms'] > 15000:
        fail(f"retrieval p95 {retrieval['p95_ms']}ms exceeds 15s")

    slow = report['slow_provider']
    if slow['health_status'] != 200:
        fail('gateway health failed while a provider was slow')
    if slow['health_ms_during_load'] > 2000:
        fail(f"gateway health took {slow['health_ms_during_load']}ms during slow provider")
    if not slow['cancel_accepted']:
        fail('cancellation was not accepted during a slow provider call')
    if slow['completed'] + slow['cancelled'] != slow['requests']:
        fail(f"slow provider completed {slow['completed']} + cancelled {slow['cancelled']} "
             f"of {slow['requests']}")
    if slow['cancelled'] < 1:
        fail('cancellation did not produce a terminal agent.cancelled event')

    for group in ('resources', 'resources_peak'):
        for service, usage in report.get(group, {}).items():
            if usage['memory_mb'] > 1024:
                fail(f'{service} memory {usage["memory_mb"]}MiB exceeds 1GiB')

    if args.baseline:
        with open(args.baseline) as handle:
            compare(report, json.load(handle))
        print(f'performance baseline comparison: passed ({args.baseline})')
    print('performance report: passed')
    print(json.dumps({key: report[key] for key in
                      ('ingestion', 'chat', 'retrieval', 'slow_provider',
                       'resources', 'resources_peak')},
                     indent=2, sort_keys=True), file=sys.stderr)


if __name__ == '__main__':
    main()
