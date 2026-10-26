#!/usr/bin/env python3
"""Static security checks for deployment configuration; no Docker daemon needed."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
errors: list[str] = []


def read(path: str) -> str:
    return (ROOT / path).read_text()


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def service_blocks(text: str) -> dict[str, str]:
    match = re.search(r'^services:\n(.*?)(?=^\S)', text, re.M | re.S)
    if not match:
        return {}
    body = match.group(1)
    starts = list(re.finditer(r'^  ([a-z0-9_-]+):\n', body, re.M))
    blocks: dict[str, str] = {}
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        blocks[start.group(1)] = body[start.start():end]
    return blocks


def published_ports(block: str) -> list[str]:
    match = re.search(r'^    ports:\n((?:      .*\n)+)', block, re.M)
    if not match:
        return []
    return [line.strip().lstrip('- ').strip("'\"") for line in match.group(1).splitlines()]


def loopback_binding(entry: str) -> bool:
    if entry.startswith('${'):
        default = entry.split(':-', 1)[1].split('}', 1)[0] if ':-' in entry else ''
        return default == '127.0.0.1'
    return entry.startswith('127.0.0.1:')


compose = read('compose.yaml')
env_example = read('.env.example')
blocks = service_blocks(compose)

check(bool(blocks), 'compose services could not be parsed')
for name in ('gateway', 'console', 'rustfs'):
    check(name in blocks, f'missing service {name}')
for name in ('postgres', 'runtime', 'worker', 'qdrant', 'ollama'):
    check(name in blocks, f'missing service {name}')

# Only the ingress surface is published, and only on the loopback interface.
for name, block in blocks.items():
    ports = published_ports(block)
    if name in ('gateway', 'console', 'rustfs'):
        check(bool(ports), f'{name} must publish an explicit port')
        for entry in ports:
            check(loopback_binding(entry), f'{name} publishes {entry} outside loopback')
    else:
        check(not ports, f'{name} must not publish ports: {ports}')

# Network separation: backend is internal, only provider clients join egress.
check(re.search(r'^  backend:\n    internal: true', compose, re.M) is not None,
      'backend network must be internal')
check(re.search(r'^  model-egress:\n', compose, re.M) is not None,
      'model-egress network is missing')
for name in ('runtime', 'worker'):
    check(re.search(r'networks: \[backend, model-egress\]', blocks[name]) is not None,
          f'{name} must join backend and model-egress')
    check('UAI_EGRESS_ALLOW:' in blocks[name], f'{name} must declare an egress allowlist')
check('UAI_RATE_LIMIT_PER_PRINCIPAL:' in blocks['gateway'],
      'gateway must expose the per-principal rate limit')
for name in ('postgres', 'qdrant'):
    check('model-egress' not in blocks[name] and 'frontend' not in blocks[name],
          f'{name} must stay on the backend network')

# Container hardening on the application surface.
for name in ('gateway', 'runtime', 'worker', 'console', 'qdrant', 'ollama', 'postgres'):
    block = blocks[name]
    check('privileged: true' not in block, f'{name} is privileged')
    check('network_mode: host' not in block, f'{name} uses host networking')
    if name in ('gateway', 'runtime', 'worker', 'console'):
        check('read_only: true' in block, f'{name} must use a read-only root filesystem')
        check('cap_drop: [ALL]' in block, f'{name} must drop all capabilities')
        check('no-new-privileges:true' in block, f'{name} must set no-new-privileges')
check('docker.sock' not in compose, 'docker socket must not be mounted')

# Secrets are references only; literals in compose or the example env are leaks.
secret_name = re.compile(r'^[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|KEY)[A-Z0-9_]*$')
for line in compose.splitlines():
    match = re.match(r'^\s+([A-Z0-9_]+):\s*(.*)$', line)
    if match and secret_name.fullmatch(match.group(1)):
        value = match.group(2).strip()
        check(value.startswith('${') or value == '',
              f'compose contains a literal secret for {match.group(1)}')
for name in ('POSTGRES_PASSWORD', 'INTERNAL_API_KEY', 'UAI_API_KEY_SHA256',
             'RUSTFS_ACCESS_KEY', 'RUSTFS_SECRET_KEY', 'MODEL_API_KEY',
             'EMBEDDING_API_KEY', 'ISOLATED_PLUGIN_TOKEN'):
    match = re.search(rf'^{name}=(.*)$', env_example, re.M)
    check(match is not None, f'{name} missing from .env.example')
    if match:
        check(match.group(1).strip() == '', f'.env.example contains a value for {name}')

# Egress policy is explicit and uses host:port entries.
match = re.search(r'^UAI_EGRESS_ALLOW=(.*)$', env_example, re.M)
check(match is not None, 'UAI_EGRESS_ALLOW missing from .env.example')
check(re.search(r'^UAI_RATE_LIMIT_PER_PRINCIPAL=\d+$', env_example, re.M) is not None,
      'UAI_RATE_LIMIT_PER_PRINCIPAL missing from .env.example')
if match and match.group(1).strip():
    for entry in match.group(1).split(','):
        check(re.fullmatch(r'[A-Za-z0-9.-]+:\d{1,5}', entry.strip()) is not None,
              f'invalid UAI_EGRESS_ALLOW entry: {entry}')

# TLS terminator: modern protocols, HSTS, and no proxy-owned CORS.
proxy_path = ROOT / 'deploy/reverse-proxy/nginx.conf.example'
check(proxy_path.exists(), 'reverse proxy example is missing')
if proxy_path.exists():
    proxy = proxy_path.read_text()
    check('TLSv1.2 TLSv1.3' in proxy, 'reverse proxy must require TLS 1.2/1.3')
    check('Strict-Transport-Security' in proxy, 'reverse proxy must set HSTS')
    check('gateway:8080' in proxy, 'reverse proxy must target the gateway')
    check('Access-Control-Allow-Origin' not in proxy,
          'reverse proxy must not duplicate gateway CORS policy')

for path in list((ROOT / 'deploy').rglob('*')) + list((ROOT / 'configs').rglob('*')):
    if path.is_file():
        text = path.read_text(errors='ignore')
        check('Access-Control-Allow-Origin: *' not in text,
              f'wildcard CORS in {path.relative_to(ROOT)}')

# API credentials are stored as digests only.
migration = read('apps/gateway/migrations/002_credentials_audit.sql')
check('key_digest text NOT NULL UNIQUE CHECK (length(key_digest)=64)' in migration,
      'api_credentials must store only a 64-character key digest')
for forbidden in ('api_key text', 'key text', 'secret text'):
    check(forbidden not in migration, f'plaintext credential column: {forbidden}')

if errors:
    for error in errors:
        print(f'security config: {error}', file=sys.stderr)
    raise SystemExit(1)
print('security config: ok')
