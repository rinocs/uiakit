import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { operations, type Operation } from '../src/operations.ts';

const here = dirname(fileURLToPath(import.meta.url));
const contractPath = resolve(here, '../../api-contract/public.openapi.json');
const packageDir = resolve(here, '..');

interface OpenAPIOperation {
  operationId?: string;
  parameters?: Array<{
    in?: string;
    name?: string;
    required?: boolean;
  }>;
}

interface OpenAPIDocument {
  paths: Record<
    string,
    Record<string, OpenAPIOperation | unknown>
  >;
}

test('SDK operations exactly match the public OpenAPI contract', () => {
  const document = JSON.parse(
    readFileSync(contractPath, 'utf8'),
  ) as OpenAPIDocument;
  const expected = new Map<
    string,
    {
      method: string;
      path: string;
      requiresIdempotencyKey: boolean;
      requiresIfMatch: boolean;
    }
  >();

  for (const [path, item] of Object.entries(document.paths)) {
    for (const [method, value] of Object.entries(item)) {
      if (method === 'parameters') continue;
      const operation = value as OpenAPIOperation;
      const operationId = operation.operationId;
      assert.ok(operationId, `missing operationId for ${method} ${path}`);
      const headers = [
        ...(Array.isArray((item as { parameters?: unknown }).parameters)
          ? ((item as { parameters: OpenAPIOperation['parameters'] }).parameters ?? [])
          : []),
        ...(operation.parameters ?? []),
      ];
      assert.equal(
        expected.has(operationId),
        false,
        `duplicate operationId ${operationId}`,
      );
      expected.set(operationId, {
        method: method.toUpperCase(),
        path,
        requiresIdempotencyKey: headers.some(
          (header) =>
            header?.in === 'header' &&
            header.name === 'Idempotency-Key' &&
            header.required === true,
        ),
        requiresIfMatch: headers.some(
          (header) =>
            header?.in === 'header' &&
            header.name === 'If-Match' &&
            header.required === true,
        ),
      });
    }
  }

  assert.deepEqual(Object.keys(operations).sort(), [...expected.keys()].sort());
  for (const [operationId, operation] of Object.entries(operations)) {
    const typedOperation = operation as Operation;
    assert.deepEqual(
      {
        method: typedOperation.method,
        path: typedOperation.path,
        requiresIdempotencyKey: typedOperation.requiresIdempotencyKey ?? false,
        requiresIfMatch: typedOperation.requiresIfMatch ?? false,
      },
      expected.get(operationId),
      `contract mismatch for ${operationId}`,
    );
  }
});

test('generated types are in sync with the public contract', () => {
  assert.doesNotThrow(() => {
    execFileSync(
      process.execPath,
      ['scripts/generate-types.mjs', '--check'],
      { cwd: packageDir, stdio: 'pipe' },
    );
  });
});
