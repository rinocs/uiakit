#!/usr/bin/env python3
"""License gate for the generated CycloneDX SBOM."""
from __future__ import annotations

import argparse
import json
import re
import sys

ALLOWED = {
    '0BSD', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'BlueOak-1.0.0',
    'CC0-1.0', 'ISC', 'LGPL-3.0-only', 'LGPL-3.0-or-later', 'MIT', 'MIT-0',
    'MPL-2.0', 'PostgreSQL', 'PSF-2.0', 'Python-2.0', 'Unlicense', 'Zlib',
    'GPL-3.0-only',
}


def normalize(value):
    value = value.strip()
    aliases = {
        'Apache 2.0': 'Apache-2.0',
        'Apache License 2.0': 'Apache-2.0',
        'BSD': 'BSD-3-Clause',
        'BSD License': 'BSD-3-Clause',
        'MIT License': 'MIT',
        'Python Software Foundation License': 'PSF-2.0',
        'PSF': 'PSF-2.0',
        'LGPL-3.0': 'LGPL-3.0-only',
        'MPL-2.0': 'MPL-2.0',
    }
    return aliases.get(value, value)


def expression_allowed(expression):
    expression = normalize(expression).strip('() ')
    if expression in ALLOWED:
        return True
    alternatives = re.split(r'\s+OR\s+', expression)
    if len(alternatives) > 1:
        return any(expression_allowed(item) for item in alternatives)
    terms = re.split(r'\s+AND\s+', expression)
    if len(terms) == 1:
        return terms[0].strip('() ') in ALLOWED
    return all(expression_allowed(item) for item in terms)


def component_licenses(component):
    licenses = component.get('licenses') or []
    values = []
    for entry in licenses:
        if 'expression' in entry:
            values.append(entry['expression'])
        elif isinstance(entry.get('license'), dict):
            license_data = entry['license']
            values.append(license_data.get('id') or license_data.get('name') or 'NOASSERTION')
    return values or ['NOASSERTION']


def validate(path):
    with open(path) as handle:
        sbom = json.load(handle)
    components = sbom.get('components') or []
    if not components:
        raise SystemExit('license check failed: SBOM has no components')
    rejected = []
    for component in components:
        for value in component_licenses(component):
            if not expression_allowed(value):
                rejected.append((component.get('name', '?'), component.get('version', '?'), value))
    if rejected:
        print('license check failed:', file=sys.stderr)
        for name, version, value in rejected:
            print(f' - {name} {version}: {value}', file=sys.stderr)
        raise SystemExit(1)
    return len(components)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sbom')
    args = parser.parse_args()
    count = validate(args.sbom)
    print(f'license check: passed ({count} components)')


if __name__ == '__main__':
    main()
