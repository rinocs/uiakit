#!/usr/bin/env python3
"""Release gate for M6-07: source metadata, locks, artifacts and secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r'^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')
REQUIRED_LOCKS = [
    'apps/gateway/go.sum',
    'packages/sdk-typescript/package-lock.json',
    'packages/chat-widget/package-lock.json',
    'apps/console/package-lock.json',
    'packages/sdk-php/composer.lock',
]
PYPROJECTS = [
    'apps/runtime/pyproject.toml',
    'apps/worker/pyproject.toml',
    'packages/core/pyproject.toml',
    'packages/plugin-sdk/pyproject.toml',
    'packages/fastapi/pyproject.toml',
    'plugins/examples/hello/pyproject.toml',
]
PACKAGE_JSONS = [
    'packages/sdk-typescript/package.json',
    'packages/chat-widget/package.json',
    'apps/console/package.json',
]
REQUIREMENTS = [
    'apps/runtime/requirements.txt',
    'apps/runtime/requirements-dev.txt',
    'apps/runtime/requirements-s3.txt',
    'apps/worker/requirements.txt',
]
SECRET_PATTERNS = [
    re.compile(r'(?im)^[ \t]*(UAI_API_KEY_SHA256|INTERNAL_API_KEY|POSTGRES_PASSWORD|'
               r'MODEL_API_KEY|RUSTFS_SECRET_KEY|ISOLATED_PLUGIN_TOKEN)[ \t]*=[ \t]*'
               r'(?![\$\{<])[^\s]+'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?im)^[ \t]*authorization:[ \t]*bearer[ \t]+[A-Za-z0-9._-]{20,}[ \t]*$'),
]


def fail(message):
    raise SystemExit('release check failed: ' + message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def version():
    path = ROOT / 'VERSION'
    if not path.exists():
        fail('VERSION is missing')
    value = path.read_text().strip()
    if not SEMVER.fullmatch(value):
        fail(f'VERSION is not semantic: {value!r}')
    return value


def check_versions(expected):
    observed = {}
    for relative in PYPROJECTS:
        text = (ROOT / relative).read_text()
        match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
        if not match:
            fail(f'{relative} has no version')
        observed[relative] = match.group(1)
    for relative in PACKAGE_JSONS:
        observed[relative] = json.loads((ROOT / relative).read_text())['version']
    composer = json.loads((ROOT / 'packages/sdk-php/composer.json').read_text())
    if composer.get('version') and composer['version'] != expected:
        fail('packages/sdk-php/composer.json version does not match VERSION')
    compose = (ROOT / 'compose.yaml').read_text()
    for tag in re.findall(r'image:\s*uai-[A-Za-z0-9_.-]+:([^\s]+)', compose):
        observed['compose.yaml:' + tag] = tag
    for relative, value in observed.items():
        if value != expected:
            fail(f'{relative} version {value} != VERSION {expected}')
    runtime = (ROOT / 'apps/runtime/uai_runtime/app.py').read_text()
    if f"return {{'status': 'ok', 'version': '{expected}'}}" not in runtime:
        fail('runtime health version does not match VERSION')


def check_locks():
    for relative in REQUIRED_LOCKS:
        if not (ROOT / relative).is_file():
            fail(f'lockfile missing: {relative}')
    for relative in REQUIREMENTS:
        for number, line in enumerate((ROOT / relative).read_text().splitlines(), 1):
            line = line.split('#', 1)[0].strip()
            if not line or line.startswith('-r ') or line.startswith('--'):
                continue
            if not re.fullmatch(r'[A-Za-z0-9_.-]+==[^\s]+', line):
                fail(f'{relative}:{number} is not an exact pin: {line!r}')
    for relative in ('packages/sdk-typescript/package-lock.json',
                     'packages/chat-widget/package-lock.json',
                     'apps/console/package-lock.json'):
        lock = json.loads((ROOT / relative).read_text())
        if int(lock.get('lockfileVersion', 0)) < 2:
            fail(f'{relative} is not an npm lockfile v2/v3')
    composer = json.loads((ROOT / 'packages/sdk-php/composer.lock').read_text())
    if not composer.get('content-hash'):
        fail('composer.lock has no content-hash')


def check_release_files():
    required = [
        '.github/workflows/release.yaml',
        'docs/releases.md',
        'scripts/release.py',
        'tests/release/check_licenses.py',
        'tests/release/contract_diff.py',
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f'release file missing: {relative}')
    workflow = (ROOT / '.github/workflows/release.yaml').read_text()
    for marker in ('workflow_dispatch', 'contract_diff.py', 'release.py images',
                   'grype', 'attest-build-provenance', 'upload-artifact'):
        if marker not in workflow:
            fail(f'release workflow lacks {marker}')
    for forbidden in ('npm publish', 'docker push', 'composer publish'):
        if forbidden in workflow:
            fail(f'release workflow must not publish automatically: {forbidden}')


def check_no_floating_images():
    for dockerfile in (ROOT / 'deploy/docker').glob('*.Dockerfile'):
        for line in dockerfile.read_text().splitlines():
            if line.startswith('FROM '):
                image = line.split()[1]
                if image.endswith(':latest') or (':' not in image and '@' not in image):
                    fail(f'{dockerfile.name} uses a floating base image: {line}')


def secret_free(name, data):
    if b'\0' in data:
        return
    text = data.decode('utf-8', 'ignore')
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            fail(f'possible secret in artifact: {name}')


def scan_archive(relative, path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.file_size > 5 * 1024 * 1024:
                    continue
                if member.filename.endswith(('.env', '.pem', '.key')):
                    fail(f'forbidden file in {relative}: {member.filename}')
                secret_free(f'{relative}:{member.filename}', archive.read(member))
        return
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if not member.isfile() or member.size > 5 * 1024 * 1024:
                    continue
                if member.name.endswith(('.env', '.pem', '.key')):
                    fail(f'forbidden file in {relative}: {member.name}')
                extracted = archive.extractfile(member)
                secret_free(f'{relative}:{member.name}', extracted.read() if extracted else b'')
        return
    if path.suffix in ('.env', '.pem', '.key'):
        fail(f'forbidden release file: {relative}')
    secret_free(relative, path.read_bytes())


def check_artifacts(root):
    root = Path(root)
    manifest_path = root / 'manifest.json'
    if not manifest_path.is_file():
        fail('artifact manifest.json is missing')
    manifest = json.loads(manifest_path.read_text())
    expected = version()
    if manifest.get('version') != expected:
        fail(f"artifact version {manifest.get('version')} != {expected}")
    for relative, digest in manifest.get('files', {}).items():
        path = root / relative
        if not path.is_file():
            fail(f'manifest file missing: {relative}')
        if sha256(path) != digest:
            fail(f'manifest checksum mismatch: {relative}')
    for relative in ('sbom.cdx.json', 'THIRD_PARTY_NOTICES.md', 'images.json'):
        if not (root / relative).is_file():
            fail(f'artifact missing: {relative}')
    if not list((root / 'packages').glob('*')):
        fail('no SDK/plugin packages were prepared')
    images = json.loads((root / 'images.json').read_text())
    if not images:
        fail('no images were recorded')
    for entry in images:
        for key in ('name', 'tag', 'image_id', 'tar_sha256'):
            if not entry.get(key):
                fail(f'image entry lacks {key}: {entry}')
    for path in root.rglob('*'):
        if path.is_file():
            scan_archive(str(path.relative_to(root)), path)
    sys.path.insert(0, str(Path(__file__).parent))
    from check_licenses import validate  # noqa: PLC0415
    validate(root / 'sbom.cdx.json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', action='store_true')
    parser.add_argument('--artifacts')
    args = parser.parse_args()
    expected = version()
    check_versions(expected)
    check_locks()
    check_release_files()
    check_no_floating_images()
    if args.artifacts:
        check_artifacts(args.artifacts)
    print(f'release source/artifacts: passed (version {expected})')


if __name__ == '__main__':
    main()
