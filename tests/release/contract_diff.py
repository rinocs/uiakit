#!/usr/bin/env python3
"""Detect breaking changes between two public OpenAPI documents."""
from __future__ import annotations

import argparse
import json
import sys


def resolve(spec, node):
    seen = set()
    while isinstance(node, dict) and '$ref' in node:
        ref = node['$ref']
        if not ref.startswith('#/') or ref in seen:
            break
        seen.add(ref)
        current = spec
        for part in ref[2:].split('/'):
            current = current[part.replace('~1', '/').replace('~0', '~')]
        node = current
    return node


def type_of(schema):
    value = schema.get('type')
    if value:
        return value
    if 'properties' in schema:
        return 'object'
    if 'items' in schema:
        return 'array'
    return None


def compare_schema(spec_old, spec_new, old, new, path, request, changes, seen):
    old = resolve(spec_old, old)
    new = resolve(spec_new, new)
    if not isinstance(old, dict) or not isinstance(new, dict):
        return
    key = (id(old), id(new))
    if key in seen:
        return
    seen.add(key)
    old_type, new_type = type_of(old), type_of(new)
    if old_type != new_type:
        changes.append(f'{path}: type {old_type} -> {new_type}')
        return
    old_enum = old.get('enum')
    new_enum = new.get('enum')
    if old_enum is not None and new_enum is not None:
        if not set(old_enum).issubset(set(new_enum)):
            changes.append(f'{path}: enum narrowed')
    old_props = old.get('properties', {})
    new_props = new.get('properties', {})
    for name in old_props:
        if name not in new_props:
            changes.append(f'{path}.{name}: property removed')
            continue
        compare_schema(spec_old, spec_new, old_props[name], new_props[name],
                       f'{path}.{name}', request, changes, seen)
    for name in new_props:
        if name not in old_props and request and name in new.get('required', []):
            changes.append(f'{path}.{name}: new required request property')
    if request:
        added_required = set(new.get('required', [])) - set(old.get('required', []))
        for name in sorted(added_required):
            changes.append(f'{path}.{name}: request property became required')
    if old_type == 'array' and 'items' in old and 'items' in new:
        compare_schema(spec_old, spec_new, old['items'], new['items'],
                       f'{path}[]', request, changes, seen)
    for keyword in ('allOf', 'oneOf', 'anyOf'):
        old_parts, new_parts = old.get(keyword), new.get(keyword)
        if old_parts is not None and new_parts is None:
            changes.append(f'{path}: {keyword} removed')
        elif old_parts is not None and new_parts is not None:
            for index, (left, right) in enumerate(zip(old_parts, new_parts)):
                compare_schema(spec_old, spec_new, left, right,
                               f'{path}.{keyword}[{index}]', request, changes, seen)


def operation_changes(spec_old, spec_new, path, method, old, new, changes):
    old_parameters = {(item.get('in'), item.get('name')): item
                      for item in old.get('parameters', [])}
    new_parameters = {(item.get('in'), item.get('name')): item
                      for item in new.get('parameters', [])}
    for key, parameter in old_parameters.items():
        if key not in new_parameters:
            changes.append(f'{method.upper()} {path}: parameter {key} removed')
        else:
            compare_schema(spec_old, spec_new, parameter.get('schema', {}),
                           new_parameters[key].get('schema', {}),
                           f'{method.upper()} {path} parameter {key[1]}',
                           True, changes, set())
    for key, parameter in new_parameters.items():
        if key not in old_parameters and parameter.get('required'):
            changes.append(f'{method.upper()} {path}: required parameter {key} added')

    old_body = old.get('requestBody')
    new_body = new.get('requestBody')
    if old_body and not new_body:
        changes.append(f'{method.upper()} {path}: request body removed')
    elif old_body and new_body:
        if new_body.get('required') and not old_body.get('required'):
            changes.append(f'{method.upper()} {path}: request body became required')
        old_content = old_body.get('content', {})
        new_content = new_body.get('content', {})
        for media in old_content:
            if media not in new_content:
                changes.append(f'{method.upper()} {path}: request media {media} removed')
            else:
                compare_schema(spec_old, spec_new, old_content[media].get('schema', {}),
                               new_content[media].get('schema', {}),
                               f'{method.upper()} {path} request', True, changes, set())

    old_responses = old.get('responses', {})
    new_responses = new.get('responses', {})
    for status, response in old_responses.items():
        if status not in new_responses:
            changes.append(f'{method.upper()} {path}: response {status} removed')
            continue
        old_content = resolve(spec_old, response).get('content', {}) if isinstance(response, dict) else {}
        new_content = resolve(spec_new, new_responses[status]).get('content', {})
        for media in old_content:
            if media not in new_content:
                changes.append(f'{method.upper()} {path}: response media {media} removed')
            else:
                compare_schema(spec_old, spec_new, old_content[media].get('schema', {}),
                               new_content[media].get('schema', {}),
                               f'{method.upper()} {path} response {status}', False,
                               changes, set())


def breaking_changes(spec_old, spec_new):
    changes = []
    old_paths = spec_old.get('paths', {})
    new_paths = spec_new.get('paths', {})
    for path, old_path in old_paths.items():
        if path not in new_paths:
            changes.append(f'path {path}: removed')
            continue
        new_path = new_paths[path]
        for method, old_operation in old_path.items():
            if method not in ('get', 'put', 'post', 'delete', 'patch', 'head', 'options'):
                continue
            if method not in new_path:
                changes.append(f'{method.upper()} {path}: operation removed')
                continue
            operation_changes(spec_old, spec_new, path, method,
                              old_operation, new_path[method], changes)
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('old')
    parser.add_argument('new')
    args = parser.parse_args()
    with open(args.old) as handle:
        old = json.load(handle)
    with open(args.new) as handle:
        new = json.load(handle)
    changes = breaking_changes(old, new)
    if changes:
        print('breaking public contract changes:', file=sys.stderr)
        for change in changes:
            print(' - ' + change, file=sys.stderr)
        raise SystemExit(1)
    print('public contract diff: no breaking changes')


if __name__ == '__main__':
    main()
