/**
 * A deliberately small Markdown renderer that builds DOM nodes and never
 * interprets model output as HTML. Raw HTML in the source remains text.
 */
export function renderMarkdown(source: string, document: Document): DocumentFragment {
  const fragment = document.createDocumentFragment();
  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';
    if (line.trim() === '') {
      index += 1;
      continue;
    }

    const fence = /^```([A-Za-z0-9_-]*)\s*$/.exec(line);
    if (fence) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index] ?? '')) {
        codeLines.push(lines[index] ?? '');
        index += 1;
      }
      if (index < lines.length) index += 1;
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      if (fence[1]) code.className = `language-${fence[1]}`;
      code.textContent = codeLines.join('\n');
      pre.append(code);
      fragment.append(pre);
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const element = document.createElement(`h${heading[1]?.length ?? 1}`);
      appendInline(element, heading[2] ?? '', document);
      fragment.append(element);
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index] ?? '')) {
        quoteLines.push((lines[index] ?? '').replace(/^>\s?/, ''));
        index += 1;
      }
      const quote = document.createElement('blockquote');
      const paragraph = document.createElement('p');
      appendLines(paragraph, quoteLines, document);
      quote.append(paragraph);
      fragment.append(quote);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const list = document.createElement('ul');
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index] ?? '')) {
        const item = document.createElement('li');
        appendInline(
          item,
          (lines[index] ?? '').replace(/^\s*[-*]\s+/, ''),
          document,
        );
        list.append(item);
        index += 1;
      }
      fragment.append(list);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const list = document.createElement('ol');
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index] ?? '')) {
        const item = document.createElement('li');
        appendInline(
          item,
          (lines[index] ?? '').replace(/^\s*\d+\.\s+/, ''),
          document,
        );
        list.append(item);
        index += 1;
      }
      fragment.append(list);
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length) {
      const current = lines[index] ?? '';
      if (
        current.trim() === '' ||
        /^```/.test(current) ||
        /^(#{1,3})\s+/.test(current) ||
        /^>\s?/.test(current) ||
        /^\s*[-*]\s+/.test(current) ||
        /^\s*\d+\.\s+/.test(current)
      ) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }
    const paragraph = document.createElement('p');
    appendLines(paragraph, paragraphLines, document);
    fragment.append(paragraph);
  }

  return fragment;
}

export function sanitizeLink(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed || /[\u0000-\u001F\u007F]/.test(trimmed)) return null;
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }
  if (!['https:', 'http:', 'mailto:'].includes(parsed.protocol)) return null;
  if ((parsed.protocol === 'https:' || parsed.protocol === 'http:') && !parsed.hostname) {
    return null;
  }
  if (parsed.protocol === 'mailto:' && !parsed.pathname) return null;
  return parsed.toString();
}

function appendLines(parent: Node, lines: string[], document: Document): void {
  lines.forEach((line, index) => {
    if (index > 0) parent.appendChild(document.createElement('br'));
    appendInline(parent, line, document);
  });
}

function appendInline(parent: Node, source: string, document: Document): void {
  let remaining = source;
  while (remaining.length > 0) {
    if (remaining.startsWith('`')) {
      const end = remaining.indexOf('`', 1);
      if (end > 1) {
        const code = document.createElement('code');
        code.textContent = remaining.slice(1, end);
        parent.appendChild(code);
        remaining = remaining.slice(end + 1);
        continue;
      }
    }
    if (remaining.startsWith('**')) {
      const end = remaining.indexOf('**', 2);
      if (end > 2) {
        const strong = document.createElement('strong');
        appendInline(strong, remaining.slice(2, end), document);
        parent.appendChild(strong);
        remaining = remaining.slice(end + 2);
        continue;
      }
    }
    if (remaining.startsWith('*')) {
      const end = remaining.indexOf('*', 1);
      if (end > 1) {
        const emphasis = document.createElement('em');
        appendInline(emphasis, remaining.slice(1, end), document);
        parent.appendChild(emphasis);
        remaining = remaining.slice(end + 1);
        continue;
      }
    }
    if (remaining.startsWith('[')) {
      const closeLabel = remaining.indexOf(']', 1);
      if (closeLabel > 1 && remaining[closeLabel + 1] === '(') {
        const closeUrl = remaining.indexOf(')', closeLabel + 2);
        if (closeUrl > closeLabel + 1) {
          const label = remaining.slice(1, closeLabel);
          const rawUrl = remaining.slice(closeLabel + 2, closeUrl);
          const safeUrl = sanitizeLink(rawUrl);
          if (safeUrl) {
            const link = document.createElement('a');
            link.href = safeUrl;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            appendInline(link, label, document);
            parent.appendChild(link);
          } else {
            parent.appendChild(document.createTextNode(label));
          }
          remaining = remaining.slice(closeUrl + 1);
          continue;
        }
      }
    }

    const special = nextSpecialIndex(remaining);
    const chunk = special === -1 ? remaining : remaining.slice(0, special);
    if (chunk) parent.appendChild(document.createTextNode(chunk));
    remaining = special === -1 ? '' : remaining.slice(special);
  }
}

function nextSpecialIndex(value: string): number {
  let best = -1;
  for (const token of ['`', '*', '[']) {
    const index = value.indexOf(token);
    if (index !== -1 && (best === -1 || index < best)) best = index;
  }
  return best;
}
