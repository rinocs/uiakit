# Parsing and normalization
Contracts and parsers to transform the bytes of a document into normalized text
with provenance. Parsing occurs on bytes provided by the host, without networking,
running scripts or model calls. Chunking is implemented in
[chunking.md](chunking.md); the worker is M3-06 ([jobs.md](jobs.md)), the index
vector is M3-09.

## Core contracts

`packages/core/src/uai_core/documents.py`:

- `DocumentLoader`: `media_type`, `source`, `load() -> bytes`.
- `BytesLoader`: in-memory loader for upload/test.
- `DocumentParser`: `media_types`, `parse(data, source=...) -> ParsedDocument`.
- `DocumentProcessor`: parser registry, byte/char limits and
  `process_loader`.
- `ParsedDocument`: `media_type`, `source`, normalized `text`, `pages`.
- `DocumentPage`: page number, text and `start`/`end` offset in the text
  normalized; the text on the page must match the slice.
- Stable errors: `CorruptDocument`, `UnsupportedDocument`, `DocumentLimit`,
  `UnsupportedBackend`.

`OcrProvider`, `SqlConnector`, `WebLoader` and `GitLoader` are contracts for
future backends. There is no dummy implementation - an absent backend must
fail with `UnsupportedBackend`/`UnsupportedDocument`, return no text
invented. The sources are configured by the host; no URL/path comes from
model or from untrusted content.

## Formats

| Format | Media type | Implementation |
| --- | --- | --- |
| TXT | `text/plain` | UTF-8 (BOM allowed), row normalization |
| Markdown | `text/markdown` | UTF-8 text preserved (syntax included) |
| HTML | `text/html` | stdlib parser, `script`/`style` excluded, entities decoded |
| Textual PDF | `application/pdf` | `pypdf`, one page per page PDF |
| DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | ZIP + `word/document.xml` with `defusedxml` |

Normalization converts `\r\n`/`\r` to `\n`, removes NULs and trailing spaces of
row, and apply `strip` to the edges. For PDFs the pages are joined with two newlines;
offsets remain consistent and verifiable.

## Limits and security

- Input: 20 MiB; normalized text: 2,000,000 characters.
- PDF: maximum 2,000 pages; Encrypted PDF not supported; PDF without text
  extractable → `UnsupportedDocument('ocr_required')` (unsimulated OCR).
- DOCX: maximum 1,000 entries, 32 MiB per entry, 64 MiB total decompressed; macros
  `vbaProject.bin`, encrypted entries, absolute path/traversal and invalid XML
  are rejected. `defusedxml` avoids dangerous entity expansions.
- HTML: no fetch of `src`/link, no script execution; the content
  remains an inert text.
- A corrupt/unreadable document fails before creating chunk or index.
- Error messages are stable codes and do not include text, path or
  credentials.

## Fixtures and tests

`tests/fixtures/documents/` contains TXT, Markdown, HTML, Two-Page PDF, PDF
without text, valid DOCX, DOCX with macros and corrupt files; the script
`generate_fixtures.py` regenerates them without external dependencies.

`apps/runtime/tests/test_parsers.py` covers the five formats, normalization,
offset/pages, unscripted HTML/fetch, corrupt PDF/OCR, hostile DOCX, limits
byte/entry and parser registry. Evidence: `make test` with 221 Python runtime tests + 8 workers
passed + 3 skipped.