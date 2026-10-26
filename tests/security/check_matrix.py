#!/usr/bin/env python3
"""Validate the security regression matrix against the repository.

Every trust boundary must name at least one deny and one allow test. Referenced
tests must still exist, and every referenced E2E script must be scheduled by
tests/e2e/run.sh. This prevents security coverage from silently disappearing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = Path(__file__).with_name('matrix.json')

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def test_exists(reference: str) -> bool:
    try:
        path_text, name = reference.split('::', 1)
    except ValueError:
        fail(f'malformed reference: {reference}')
        return False
    path = ROOT / path_text
    if not path.is_file():
        fail(f'missing test file: {path_text}')
        return False
    text = path.read_text()
    if path.suffix == '.go':
        pattern = rf'^func {re.escape(name)}\(t \*testing\.T\)'
    elif path.suffix == '.py':
        pattern = rf'^def {re.escape(name)}\s*\('
    elif path.suffix == '.ts':
        pattern = rf"""(?:test|it)\(\s*(['"`]){re.escape(name)}\1"""
    else:
        fail(f'unsupported test file type: {path_text}')
        return False
    if re.search(pattern, text, re.M) is None:
        fail(f'missing test {name} in {path_text}')
        return False
    return True


def run_referenced(boundaries: dict) -> None:
    go_tests: set[str] = set()
    python_tests: list[str] = []
    typescript = False
    for entry in boundaries.values():
        for side in ('deny', 'allow'):
            for reference in entry.get(side, []):
                path_text, name = reference.split('::', 1)
                if path_text.endswith('.go'):
                    go_tests.add(name)
                elif path_text.endswith('.py') and path_text.startswith('apps/runtime/'):
                    python_tests.append(path_text[len('apps/runtime/'):] + '::' + name)
                elif path_text.endswith('.ts'):
                    typescript = True
    env = os.environ.copy()
    git = ROOT / '.git'
    if git.is_dir() and not any(git.iterdir()):
        env['GOFLAGS'] = (env.get('GOFLAGS', '') + ' -buildvcs=false').strip()
    if go_tests:
        names = '|'.join(sorted(re.escape(name) for name in go_tests))
        subprocess.run(['go', 'test', '-run', f'^({names})$', './...'],
                       cwd=ROOT / 'apps/gateway', env=env, check=True)
    if python_tests:
        python = ROOT / 'apps/runtime/.venv/bin/python'
        executable = str(python) if python.exists() else sys.executable
        subprocess.run([executable, '-m', 'pytest', '-q', *python_tests],
                       cwd=ROOT / 'apps/runtime', check=True)
    if typescript:
        subprocess.run(['npm', 'test', '--prefix', 'packages/chat-widget'],
                       cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='execute the referenced tests')
    args = parser.parse_args()
    matrix = json.loads(MATRIX.read_text())
    required = matrix.get('required', [])
    boundaries = matrix.get('boundaries', {})
    if len(required) != len(set(required)):
        fail('required boundary names are not unique')
    missing = set(required) - set(boundaries)
    unknown = set(boundaries) - set(required)
    for name in sorted(missing):
        fail(f'missing boundary: {name}')
    for name in sorted(unknown):
        fail(f'boundary not declared in required: {name}')

    run_sh = (ROOT / 'tests/e2e/run.sh').read_text()
    compose_e2e = (ROOT / 'tests/e2e/compose.yaml').read_text()

    def scheduled(script: str) -> bool:
        if script in run_sh:
            return True
        for source, target in re.findall(r'^\s*-\s*\./([^:]+):(/app/[^:]+):ro\s*$',
                                         compose_e2e, re.M):
            if source.strip() == script and target in run_sh:
                return True
        return False

    for name, entry in boundaries.items():
        for side in ('deny', 'allow'):
            references = entry.get(side, [])
            if not references:
                fail(f'{name}: no {side} case')
            for reference in references:
                test_exists(reference)
        for script in entry.get('e2e', []):
            path = ROOT / script
            if not path.is_file():
                fail(f'{name}: missing E2E script {script}')
            elif not scheduled(script):
                fail(f'{name}: E2E script {script} is not scheduled by run.sh')
        for command in entry.get('suite', []):
            if command not in ('make test-widget', 'make test-security'):
                fail(f'{name}: unsupported suite command {command}')

    if errors:
        for error in errors:
            print(f'security matrix: {error}', file=sys.stderr)
        return 1
    if args.run:
        run_referenced(boundaries)
    print(f'security matrix: {len(boundaries)} boundaries, '
          f'{sum(len(v.get("deny", [])) + len(v.get("allow", [])) for v in boundaries.values())} test references')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
