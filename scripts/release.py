#!/usr/bin/env python3
"""Prepare a reproducible, non-publishing release bundle for Universal AI Kit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKFILES = [
    'apps/runtime/requirements.txt',
    'apps/runtime/requirements-dev.txt',
    'apps/runtime/requirements-s3.txt',
    'apps/worker/requirements.txt',
    'apps/gateway/go.mod',
    'apps/gateway/go.sum',
    'packages/sdk-typescript/package-lock.json',
    'packages/chat-widget/package-lock.json',
    'apps/console/package-lock.json',
    'packages/sdk-php/composer.json',
    'packages/sdk-php/composer.lock',
]
REQUIREMENTS = [
    'apps/runtime/requirements.txt',
    'apps/runtime/requirements-dev.txt',
    'apps/runtime/requirements-s3.txt',
    'apps/worker/requirements.txt',
]
PYTHON_PACKAGES = [
    'packages/core',
    'packages/plugin-sdk',
    'plugins/examples/hello',
]
NPM_PACKAGES = [
    'packages/sdk-typescript',
    'packages/chat-widget',
]
IMAGES = [
    ('gateway', 'deploy/docker/gateway.Dockerfile'),
    ('runtime', 'deploy/docker/runtime.Dockerfile'),
    ('worker', 'deploy/docker/worker.Dockerfile'),
    ('console', 'deploy/docker/console.Dockerfile'),
    ('isolated-plugin', 'deploy/docker/isolated-plugin.Dockerfile'),
]
PYTHON_LICENSES = {
    'annotated-doc': 'MIT', 'annotated-types': 'MIT', 'anyio': 'MIT',
    'boto3': 'Apache-2.0', 'botocore': 'Apache-2.0', 'certifi': 'MPL-2.0',
    'click': 'BSD-3-Clause', 'defusedxml': 'PSF-2.0', 'fastapi': 'MIT',
    'h11': 'MIT', 'httpcore': 'BSD-3-Clause', 'httpx': 'BSD-3-Clause',
    'idna': 'BSD-3-Clause', 'iniconfig': 'MIT', 'jmespath': 'MIT',
    'jsonschema': 'MIT', 'opentelemetry-api': 'Apache-2.0',
    'opentelemetry-sdk': 'Apache-2.0', 'packaging': 'Apache-2.0',
    'pluggy': 'MIT', 'psycopg': 'LGPL-3.0-only', 'psycopg-binary': 'LGPL-3.0-only',
    'pydantic': 'MIT', 'pydantic-core': 'MIT', 'pypdf': 'BSD-3-Clause',
    'pygments': 'BSD-2-Clause', 'pytest': 'MIT', 'python-dateutil': 'Apache-2.0',
    's3transfer': 'Apache-2.0', 'setuptools': 'MIT', 'six': 'MIT',
    'starlette': 'BSD-3-Clause', 'typing-inspection': 'MIT',
    'typing-extensions': 'PSF-2.0', 'urllib3': 'MIT', 'uvicorn': 'BSD-3-Clause',
}
GO_LICENSES = {
    'github.com/cenkalti/backoff': 'MIT',
    'github.com/go-chi/chi': 'MIT',
    'github.com/go-logr/logr': 'Apache-2.0',
    'github.com/go-logr/stdr': 'Apache-2.0',
    'github.com/google/uuid': 'BSD-3-Clause',
    'github.com/grpc-ecosystem/grpc-gateway': 'BSD-3-Clause',
    'github.com/jackc/pgpassfile': 'MIT',
    'github.com/jackc/pgservicefile': 'MIT',
    'github.com/jackc/pgx': 'MIT',
    'github.com/jackc/puddle': 'MIT',
    'go.opentelemetry.io/': 'Apache-2.0',
    'golang.org/x/': 'BSD-3-Clause',
    'google.golang.org/genproto': 'Apache-2.0',
    'google.golang.org/grpc': 'Apache-2.0',
    'google.golang.org/protobuf': 'BSD-3-Clause',
}
FIRST_PARTY = [
    ('universal-ai-kit', 'application'), ('uai-core', 'library'),
    ('uai-runtime', 'application'), ('uai-worker', 'application'),
    ('uai-plugin-sdk', 'library'), ('uai-plugin-hello', 'library'),
    ('@universal-ai-kit/sdk', 'library'), ('@universal-ai-kit/chat-widget', 'library'),
    ('@universal-ai-kit/console', 'application'),
    ('github.com/universal-ai-kit/sdk-go', 'library'),
    ('universal-ai-kit/sdk-php', 'library'),
]
ARCHIVE_EXCLUDES = {
    '.git', '.venv', '.svelte-kit', 'node_modules', 'vendor', '__pycache__',
    '.pytest_cache', 'release', 'site', 'dist', 'build', '.agents', '.superpowers', 'data',
}


def version():
    return (ROOT / 'VERSION').read_text().strip()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(command, *, cwd=ROOT, env=None):
    print('+ ' + ' '.join(str(part) for part in command), file=sys.stderr)
    subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)


def normalize_license(value):
    aliases = {
        'Apache 2.0': 'Apache-2.0', 'Apache License 2.0': 'Apache-2.0',
        'BSD': 'BSD-3-Clause', 'BSD License': 'BSD-3-Clause',
        'MIT License': 'MIT', 'PSF': 'PSF-2.0',
        'Python Software Foundation License': 'PSF-2.0',
        'LGPL-3.0': 'LGPL-3.0-only',
    }
    return aliases.get(value.strip(), value.strip())


def python_license(name):
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return PYTHON_LICENSES.get(name.lower().replace('_', '-'), 'NOASSERTION')
    expression = distribution.metadata.get('License-Expression')
    if expression:
        return normalize_license(expression)
    for classifier in distribution.metadata.get_all('Classifier') or []:
        prefix = 'License :: OSI Approved :: '
        if classifier.startswith(prefix):
            candidate = classifier[len(prefix):]
            for key, value in {
                'MIT License': 'MIT', 'BSD License': 'BSD-3-Clause',
                'Apache Software License': 'Apache-2.0',
                'Python Software Foundation License': 'PSF-2.0',
                'Mozilla Public License 2.0 (MPL 2.0)': 'MPL-2.0',
                'GNU Lesser General Public License v3 (LGPLv3)': 'LGPL-3.0-only',
                'ISC License (ISCL)': 'ISC', 'The Unlicense (Unlicense)': 'Unlicense',
                'Zlib': 'Zlib',
            }.items():
                if candidate == key:
                    return value
    license_field = (distribution.metadata.get('License') or '').strip()
    if license_field and len(license_field) <= 80:
        return normalize_license(license_field)
    return PYTHON_LICENSES.get(name.lower().replace('_', '-'), 'NOASSERTION')


def parse_requirements(path):
    for line in path.read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or line.startswith('-r ') or line.startswith('--'):
            continue
        name, pinned = line.split('==', 1)
        yield name, pinned


def python_components():
    components = {}
    for relative in REQUIREMENTS:
        for name, pinned in parse_requirements(ROOT / relative):
            purl = f'pkg:pypi/{name.lower().replace("_", "-")}@{pinned}'
            components[purl] = {
                'type': 'library', 'name': name, 'version': pinned, 'purl': purl,
                'licenses': [{'license': {'id': python_license(name)}}],
            }
    return components


def npm_components():
    components = {}
    for relative in ('packages/sdk-typescript/package-lock.json',
                     'packages/chat-widget/package-lock.json',
                     'apps/console/package-lock.json'):
        lock = json.loads((ROOT / relative).read_text())
        for key, entry in lock.get('packages', {}).items():
            if not key or not entry.get('version') or key.startswith('../'):
                continue
            name = entry.get('name') or key.split('node_modules/')[-1]
            license_data = entry.get('license') or 'NOASSERTION'
            if isinstance(license_data, list):
                license_items = [{'license': {'id': normalize_license(item)}}
                                 for item in license_data]
            else:
                license_items = [{'license': {'id': normalize_license(license_data)}}]
            purl = f'pkg:npm/{name}@{entry["version"]}'
            components[purl] = {'type': 'library', 'name': name,
                                'version': entry['version'], 'purl': purl,
                                'licenses': license_items}
    return components


def composer_components():
    components = {}
    lock = json.loads((ROOT / 'packages/sdk-php/composer.lock').read_text())
    for section in ('packages', 'packages-dev'):
        for entry in lock.get(section, []):
            name = entry['name']
            version_value = entry['version'].lstrip('v')
            licenses = entry.get('license') or ['NOASSERTION']
            purl = f'pkg:composer/{name}@{version_value}'
            components[purl] = {
                'type': 'library', 'name': name, 'version': version_value, 'purl': purl,
                'scope': 'required' if section == 'packages' else 'optional',
                'licenses': [{'license': {'id': normalize_license(item)}}
                             for item in licenses],
            }
    return components


def go_license(module):
    for prefix, license_id in GO_LICENSES.items():
        normalized = prefix.rstrip('/')
        if module == normalized or module.startswith(normalized + '/'):
            return license_id
    return 'NOASSERTION'


def go_components():
    components = {}
    path = ROOT / 'apps/gateway/go.mod'
    in_block = False
    for line in path.read_text().splitlines():
        line = line.split('//', 1)[0].strip()
        if line == 'require (':
            in_block = True
            continue
        if in_block and line == ')':
            in_block = False
            continue
        if in_block or line.startswith('require '):
            value = line[8:].strip() if line.startswith('require ') else line
            parts = value.split()
            if len(parts) < 2:
                continue
            module, module_version = parts[0], parts[1]
            purl = f'pkg:golang/{module}@{module_version}'
            components[purl] = {
                'type': 'library', 'name': module, 'version': module_version,
                'purl': purl,
                'licenses': [{'license': {'id': go_license(module)}}],
            }
    return components


def all_components():
    components = {}
    for source in (python_components(), npm_components(), composer_components(), go_components()):
        components.update(source)
    project_version = version()
    for name, component_type in FIRST_PARTY:
        purl = f'pkg:generic/{name}@{project_version}'
        components[purl] = {
            'type': component_type, 'name': name, 'version': project_version,
            'purl': purl, 'licenses': [{'license': {'id': 'LicenseRef-Proprietary'}}],
        }
    return [components[key] for key in sorted(components)]


def write_inventory(output):
    output.mkdir(parents=True, exist_ok=True)
    components = all_components()
    sbom = {
        'bomFormat': 'CycloneDX', 'specVersion': '1.5', 'version': 1,
        'metadata': {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'component': {'type': 'application', 'name': 'universal-ai-kit',
                          'version': version(),
                          'licenses': [{'license': {'id': 'LicenseRef-Proprietary'}}]},
        },
        'components': components,
    }
    (output / 'sbom.cdx.json').write_text(json.dumps(sbom, indent=2, sort_keys=True) + '\n')
    lines = [
        '# Third-party notices', '',
        'Generated from the locked dependency manifests. The project itself is',
        'proprietary (`LicenseRef-Proprietary`); this file does not grant a license',
        'to the project code. Review the upstream license text before redistribution.', '',
        '| Ecosystem | Component | Version | License |',
        '|---|---|---|---|',
    ]
    for component in components:
        licenses = ', '.join(
            entry.get('expression') or entry.get('license', {}).get('id')
            or entry.get('license', {}).get('name') or 'NOASSERTION'
            for entry in component.get('licenses', [])
        )
        ecosystem = component.get('purl', '').split('/')[0].replace('pkg:', '')
        lines.append(f"| {ecosystem} | {component['name']} | {component['version']} | {licenses} |")
    (output / 'THIRD_PARTY_NOTICES.md').write_text('\n'.join(lines) + '\n')
    print(f'inventory: {len(components)} components', file=sys.stderr)


def source_archive(output):
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'universal-ai-kit-{version()}-src.tar.gz'
    prefix = f'universal-ai-kit-{version()}'
    with tarfile.open(target, 'w:gz') as archive:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if any(part in ARCHIVE_EXCLUDES for part in relative.parts):
                continue
            if path.is_file() and path.suffix not in ('.pyc', '.pyo'):
                if relative.as_posix() == 'apps/gateway/gateway':
                    continue
                archive.add(path, arcname=str(Path(prefix) / relative))
    return target


def prepare_packages(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for package in NPM_PACKAGES:
        run(['npm', 'pack', '--pack-destination', output], cwd=ROOT / package)
    for package in PYTHON_PACKAGES:
        run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
             '--wheel-dir', output, '.'], cwd=ROOT / package)
    run(['composer', 'archive', '--format=zip', '--dir', output,
         '--file', f'sdk-php-{version()}'], cwd=ROOT / 'packages/sdk-php')
    target = output / f'sdk-go-{version()}.tar.gz'
    with tarfile.open(target, 'w:gz') as archive:
        for path in sorted((ROOT / 'packages/sdk-go').rglob('*')):
            if path.is_file() and path.suffix != '.pyc':
                archive.add(path, arcname=str(Path(f'sdk-go-{version()}') /
                                              path.relative_to(ROOT / 'packages/sdk-go')))
    source_archive(output)


def revision():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def prepare_images(output):
    root = output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    image_dir = root / 'images'
    image_dir.mkdir(parents=True, exist_ok=True)
    project_version, commit = version(), revision()
    images = []
    for name, dockerfile in IMAGES:
        tag = f'uai-{name}:{project_version}'
        run(['docker', 'build', '-f', dockerfile,
             '--build-arg', f'VERSION={project_version}',
             '--build-arg', f'REVISION={commit}', '-t', tag, '.'])
        archive = image_dir / f'uai-{name}-{project_version}.tar'
        run(['docker', 'save', '-o', archive, tag])
        image_id = subprocess.check_output(
            ['docker', 'inspect', '--format', '{{.Id}}', tag], cwd=ROOT, text=True).strip()
        labels = json.loads(subprocess.check_output(
            ['docker', 'inspect', '--format', '{{json .Config.Labels}}', tag],
            cwd=ROOT, text=True))
        images.append({'name': f'uai-{name}', 'tag': project_version,
                       'image_id': image_id, 'tar': archive.name,
                       'tar_sha256': sha256(archive), 'labels': labels})
    (output / 'images.json').write_text(json.dumps(images, indent=2, sort_keys=True) + '\n')
    print(f'images: {len(images)} built and saved', file=sys.stderr)


def prepare_manifest(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for relative in ('RELEASE_NOTES.md', 'docs/acceptance-report.md'):
        source = ROOT / relative
        if source.is_file():
            shutil.copy2(source, output / source.name)
    contract = ROOT / 'packages/api-contract/public.openapi.json'
    files = {}
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name not in ('manifest.json', 'SHA256SUMS'):
            files[str(path.relative_to(output))] = sha256(path)
    manifest = {
        'version': version(),
        'commit': revision(),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'contract_sha256': sha256(contract),
        'lockfiles': {relative: sha256(ROOT / relative) for relative in LOCKFILES},
        'files': files,
        'images': json.loads((output / 'images.json').read_text())
        if (output / 'images.json').is_file() else [],
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    sums = []
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name != 'SHA256SUMS':
            sums.append(f'{sha256(path)}  {path.relative_to(output)}')
    (output / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name in ('inventory', 'packages', 'images', 'manifest'):
        command = subparsers.add_parser(name)
        command.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if args.command == 'inventory':
        write_inventory(output)
    elif args.command == 'packages':
        prepare_packages(output)
    elif args.command == 'images':
        prepare_images(output)
    elif args.command == 'manifest':
        prepare_manifest(output)


if __name__ == '__main__':
    main()
