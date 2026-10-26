import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import { renderMarkdown, sanitizeLink } from '../src/markdown.ts';

const document = new JSDOM('<!doctype html>').window.document;

function render(source: string): DocumentFragment {
  return renderMarkdown(source, document);
}

test('renders safe Markdown without interpreting raw HTML', () => {
  const fragment = render(
    '# Title\n\nHello **world** and *you* with `code`.\n\n- one\n- two\n\n```js\nconst x = 1;\n```',
  );
  const container = document.createElement('div');
  container.append(fragment);

  assert.ok(container.querySelector('h1'));
  assert.equal(container.querySelector('strong')?.textContent, 'world');
  assert.equal(container.querySelector('em')?.textContent, 'you');
  assert.equal(container.querySelector('code')?.textContent, 'code');
  assert.equal(container.querySelectorAll('li').length, 2);
  assert.match(container.querySelector('pre')?.textContent ?? '', /const x = 1/);
});

test('does not execute raw HTML or unsafe links', () => {
  const fragment = render(
    '<img src=x onerror=alert(1)> [click](javascript:alert(1)) [safe](https://example.com)',
  );
  const container = document.createElement('div');
  container.append(fragment);

  assert.equal(container.querySelector('img'), null);
  assert.equal(container.querySelector('script'), null);
  assert.match(container.textContent ?? '', /<img src=x/);
  const links = [...container.querySelectorAll('a')];
  assert.equal(links.length, 1);
  assert.equal(links[0]?.getAttribute('href'), 'https://example.com/');
  assert.equal(links[0]?.getAttribute('rel'), 'noopener noreferrer');
  assert.equal(links[0]?.getAttribute('target'), '_blank');
  assert.equal(
    links.some((link) => (link.getAttribute('href') ?? '').includes('javascript')),
    false,
  );
});

test('rejects dangerous and relative URLs', () => {
  for (const value of [
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    '//evil.example',
    '/relative',
    'file:///etc/passwd',
    'https://example.com/\u0000',
  ]) {
    assert.equal(sanitizeLink(value), null, value);
  }
  assert.equal(sanitizeLink('mailto:support@example.com'), 'mailto:support@example.com');
});
