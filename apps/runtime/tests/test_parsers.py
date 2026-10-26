from pathlib import Path

import pytest

from uai_core.documents import (
    BytesLoader, CorruptDocument, DocumentLimit, DocumentProcessor, UnsupportedDocument,
    normalize_text,
)
from uai_runtime.rag import default_processor
from uai_runtime.rag import parsers

FIXTURES = Path(__file__).resolve().parents[3] / 'tests' / 'fixtures' / 'documents'


def fixture(name):
    return (FIXTURES / name).read_bytes()


def test_txt_markdown_and_html_are_normalized_with_provenance():
    processor = default_processor()
    txt = processor.process(fixture('sample.txt'), 'text/plain', 'sample.txt')
    assert txt.text == 'Hello TXT\nUnicode: caffè'
    assert txt.pages[0].text == txt.text[txt.pages[0].start:txt.pages[0].end]
    md = processor.process(fixture('sample.md'), 'text/markdown', 'sample.md')
    assert md.text.startswith('# Title') and '**markdown**' in md.text
    html = processor.process(fixture('sample.html'), 'text/html', 'sample.html')
    assert 'Hello' in html.text and 'World & friends' in html.text
    assert 'alert' not in html.text and 'body{}' not in html.text and 'example.invalid' not in html.text
    assert html.pages[0].text == html.text[html.pages[0].start:html.pages[0].end]


def test_pdf_preserves_pages_and_offsets():
    doc = default_processor().process(fixture('sample.pdf'), 'application/pdf', 'sample.pdf')
    assert [page.number for page in doc.pages] == [1, 2]
    assert [page.text for page in doc.pages] == ['Page one', 'Page two']
    assert doc.text == 'Page one\n\nPage two'
    for page in doc.pages:
        assert page.text == doc.text[page.start:page.end]


def test_docx_paragraphs_are_extracted():
    doc = default_processor().process(
        fixture('sample.docx'),
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'sample.docx')
    assert doc.text == 'First paragraph\nSecond paragraph'
    assert doc.pages[0].text == doc.text


def test_corrupt_documents_fail_closed():
    processor = default_processor()
    with pytest.raises(CorruptDocument):
        processor.process(fixture('corrupt.pdf'), 'application/pdf', 'corrupt.pdf')
    with pytest.raises(CorruptDocument):
        processor.process(fixture('corrupt.docx'),
                          'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'corrupt.docx')
    with pytest.raises(CorruptDocument):
        processor.process(b'\xff\xfe', 'text/plain', 'bad.txt')
    with pytest.raises(CorruptDocument):
        processor.process(b'', 'text/plain', 'empty.txt')
    with pytest.raises(CorruptDocument):
        processor.process(fixture('hostile.docx'),
                          'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'hostile.docx')
    with pytest.raises(UnsupportedDocument):
        processor.process(fixture('no_text.pdf'), 'application/pdf', 'scan.pdf')


def test_unsupported_media_and_limits(monkeypatch):
    processor = default_processor()
    with pytest.raises(UnsupportedDocument):
        processor.process(b'hello', 'application/msword')
    monkeypatch.setattr('uai_core.documents.MAX_DOCUMENT_BYTES', 4)
    with pytest.raises(DocumentLimit):
        processor.process(b'hello', 'text/plain')
    monkeypatch.setattr(parsers, 'MAX_DOCX_ENTRIES', 1)
    with pytest.raises(DocumentLimit):
        processor.process(fixture('sample.docx'),
                          'application/vnd.openxmlformats-officedocument.wordprocessingml.document')


def test_loader_registry_and_duplicate_registration():
    processor = default_processor()
    doc = processor.process_loader(BytesLoader(b'hello', 'text/plain', 'loader.txt'))
    assert doc.text == 'hello'
    with pytest.raises(ValueError):
        DocumentProcessor((parsers.TxtParser(), parsers.TxtParser()))


def test_normalize_text_removes_nul_and_normalizes_newlines():
    assert normalize_text('a\r\nb\rc\x00\n') == 'a\nb\nc'
