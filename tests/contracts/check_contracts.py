"""Check the Go/TypeScript/PHP SDK operation maps against the public OpenAPI."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = json.loads((ROOT / 'tests/contracts/sdk-matrix.json').read_text())


def expected_operations() -> dict[str, dict[str, object]]:
    document = json.loads((ROOT / MATRIX['public_openapi']).read_text())
    expected: dict[str, dict[str, object]] = {}
    for path, item in document['paths'].items():
        for method, operation in item.items():
            if method == 'parameters':
                continue
            parameters = list(item.get('parameters', [])) + list(operation.get('parameters', []))
            headers = {
                parameter['name']
                for parameter in parameters
                if parameter.get('in') == 'header' and parameter.get('required') is True
            }
            expected[operation['operationId']] = {
                'method': method.upper(),
                'path': path,
                'requiresIdempotencyKey': 'Idempotency-Key' in headers,
                'requiresIfMatch': 'If-Match' in headers,
            }
    return expected


def parse_typescript(path: Path) -> dict[str, dict[str, object]]:
    lines = path.read_text().splitlines()
    operations: dict[str, dict[str, object]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        single = re.match(r'^  (\w+): \{ (.*) \},$', line)
        if single:
            body = single.group(2)
            add_operation(operations, single.group(1), body, "method: '", "path: '", "'", "requiresIdempotencyKey: true", "requiresIfMatch: true")
            index += 1
            continue
        opening = re.match(r'^  (\w+): \{$', line)
        if opening:
            body_lines = []
            index += 1
            while index < len(lines) and lines[index].strip() != '},':
                body_lines.append(lines[index].strip())
                index += 1
            index += 1
            add_operation(operations, opening.group(1), '\n'.join(body_lines), "method: '", "path: '", "'", "requiresIdempotencyKey: true", "requiresIfMatch: true")
            continue
        index += 1
    return operations


def parse_go(path: Path) -> dict[str, dict[str, object]]:
    operations: dict[str, dict[str, object]] = {}
    for line in path.read_text().splitlines():
        match = re.match(r'^\s*"(\w+)":\s*\{(.*)\},?$', line)
        if not match:
            continue
        body = match.group(2)
        method = re.search(r'Method: "([A-Z]+)"', body)
        target = re.search(r'Path: "([^"]+)"', body)
        if method and target:
            operations[match.group(1)] = {
                'method': method.group(1),
                'path': target.group(1),
                'requiresIdempotencyKey': 'RequiresIdempotencyKey: true' in body,
                'requiresIfMatch': 'RequiresIfMatch: true' in body,
            }
    return operations


def add_operation(operations, operation_id, body, method_prefix, path_prefix, quote, idempotency, if_match):
    method = re.search(re.escape(method_prefix) + r'([A-Z]+)' + re.escape(quote), body)
    target = re.search(re.escape(path_prefix) + r'([^' + re.escape(quote) + r']+)' + re.escape(quote), body)
    if method and target:
        operations[operation_id] = {
            'method': method.group(1),
            'path': target.group(1),
            'requiresIdempotencyKey': idempotency in body,
            'requiresIfMatch': if_match in body,
        }


def parse_php(path: Path) -> dict[str, dict[str, object]]:
    source = path.read_text()
    operations: dict[str, dict[str, object]] = {}
    for match in re.finditer(r"'(\w+)' => \[(.*?)\]", source, re.DOTALL):
        body = match.group(2)
        method = re.search(r"'method' => '([A-Z]+)'", body)
        target = re.search(r"'path' => '([^']+)'", body)
        if method and target:
            operations[match.group(1)] = {
                'method': method.group(1),
                'path': target.group(1),
                'requiresIdempotencyKey': "'idempotency' => true" in body,
                'requiresIfMatch': "'ifMatch' => true" in body,
            }
    return operations


PARSERS = {
    'typescript': parse_typescript,
    'go': parse_go,
    'php': parse_php,
}


def compare(name: str, actual: dict[str, dict[str, object]], expected: dict[str, dict[str, object]]) -> list[str]:
    errors: list[str] = []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing:
        errors.append(f'{name}: missing operations {missing}')
    if extra:
        errors.append(f'{name}: extra operations {extra}')
    for operation_id in sorted(set(expected) & set(actual)):
        if actual[operation_id] != expected[operation_id]:
            errors.append(
                f'{name}: {operation_id} mismatch: {actual[operation_id]} != {expected[operation_id]}',
            )
    return errors


def main() -> int:
    expected = expected_operations()
    errors: list[str] = []
    print(f'Public OpenAPI operations: {len(expected)}')
    print(f'{"SDK":12} {"ops":>4} {"status":>8}  command')
    for name, config in MATRIX['sdk'].items():
        package = ROOT / config['package']
        operations_path = package / config['operations']
        if not operations_path.exists():
            errors.append(f'{name}: missing {operations_path}')
            print(f'{config["language"]:12} {0:>4} {"MISSING":>8}  {config["test"]}')
            continue
        actual = PARSERS[name](operations_path)
        sdk_errors = compare(name, actual, expected)
        errors.extend(sdk_errors)
        status = 'ok' if not sdk_errors else 'FAIL'
        print(f'{config["language"]:12} {len(actual):>4} {status:>8}  {config["test"]}')
    for name, config in MATRIX['integrations'].items():
        for key in ('package', 'example', 'docs'):
            if key in config and not (ROOT / config[key]).exists():
                errors.append(f'{name}: missing {key} {config[key]}')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('SDK contract matrix: passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
