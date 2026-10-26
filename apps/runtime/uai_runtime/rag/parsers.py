"""Bounded parsers for host-owned document bytes. No network or model calls."""
import io
import re
import zipfile
from html.parser import HTMLParser as _HTMLParser
from pathlib import PurePosixPath

from uai_core.documents import (
    CorruptDocument, DocumentLimit, DocumentParser, DocumentProcessor, MAX_DOCX_ENTRIES,
    MAX_DOCX_ENTRY_BYTES, MAX_DOCX_TOTAL_BYTES, MAX_PDF_PAGES, UnsupportedBackend,
    UnsupportedDocument, document_from_pages, normalize_text,
)

_WORD = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_BLOCK = frozenset({'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                    'section', 'article', 'header', 'footer', 'table', 'ul', 'ol',
                    'blockquote', 'pre'})


def _decode(data: bytes) -> str:
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise CorruptDocument('invalid_text_encoding') from None


def _text(media_type: str, source: str, value: str):
    return document_from_pages(media_type, source, [(1, value)])


class TxtParser:
    media_types = frozenset({'text/plain'})

    def parse(self, data: bytes, *, source: str = ''):
        return _text('text/plain', source, _decode(data))


class MarkdownParser:
    media_types = frozenset({'text/markdown'})

    def parse(self, data: bytes, *, source: str = ''):
        return _text('text/markdown', source, _decode(data))


class _TextExtractor(_HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag == 'br' or tag in _BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        value = normalize_text(''.join(self.parts))
        return re.sub(r'\n{3,}', '\n\n', value)


class HtmlParser:
    media_types = frozenset({'text/html'})

    def parse(self, data: bytes, *, source: str = ''):
        extractor = _TextExtractor()
        try:
            extractor.feed(_decode(data))
            extractor.close()
        except Exception:
            raise CorruptDocument('invalid_html') from None
        return _text('text/html', source, extractor.text())


class PdfParser:
    media_types = frozenset({'application/pdf'})

    def parse(self, data: bytes, *, source: str = ''):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise UnsupportedBackend('pdf_backend_missing') from None
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise UnsupportedDocument('encrypted_pdf')
            if len(reader.pages) > MAX_PDF_PAGES:
                raise DocumentLimit('pdf_too_many_pages')
            pages = []
            for index, page in enumerate(reader.pages, 1):
                try:
                    value = page.extract_text() or ''
                except Exception:
                    raise CorruptDocument('invalid_pdf_page') from None
                pages.append((index, value))
        except (DocumentLimit, UnsupportedDocument):
            raise
        except Exception:
            raise CorruptDocument('invalid_pdf') from None
        document = document_from_pages('application/pdf', source, pages)
        if not document.text.strip():
            raise UnsupportedDocument('ocr_required')
        return document


def _validate_docx(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise CorruptDocument('invalid_docx') from None
    infos = archive.infolist()
    if len(infos) > MAX_DOCX_ENTRIES:
        archive.close()
        raise DocumentLimit('docx_too_many_entries')
    total = 0
    names = set()
    for info in infos:
        name = info.filename
        pure = PurePosixPath(name)
        if (info.flag_bits & 1 or '\\' in name or pure.is_absolute() or '..' in pure.parts
                or pure.name.lower() == 'vbaproject.bin'):
            archive.close()
            raise CorruptDocument('unsafe_docx')
        if info.file_size > MAX_DOCX_ENTRY_BYTES:
            archive.close()
            raise DocumentLimit('docx_entry_too_large')
        total += info.file_size
        if total > MAX_DOCX_TOTAL_BYTES:
            archive.close()
            raise DocumentLimit('docx_too_large')
        names.add(name)
    if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
        archive.close()
        raise CorruptDocument('invalid_docx')
    return archive


class DocxParser:
    media_types = frozenset({'application/vnd.openxmlformats-officedocument.wordprocessingml.document'})

    def parse(self, data: bytes, *, source: str = ''):
        archive = _validate_docx(data)
        try:
            try:
                from defusedxml import ElementTree
                root = ElementTree.fromstring(archive.read('word/document.xml'))
            except Exception:
                raise CorruptDocument('invalid_docx_xml') from None
            paragraphs = []
            for paragraph in root.iter(f'{{{_WORD}}}p'):
                parts = []
                for node in paragraph.iter():
                    if node.tag == f'{{{_WORD}}}t' and node.text:
                        parts.append(node.text)
                    elif node.tag == f'{{{_WORD}}}tab':
                        parts.append('\t')
                    elif node.tag in (f'{{{_WORD}}}br', f'{{{_WORD}}}cr'):
                        parts.append('\n')
                    elif node.tag == f'{{{_WORD}}}noBreakHyphen':
                        parts.append('-')
                paragraphs.append(''.join(parts))
            value = '\n'.join(paragraphs)
        finally:
            archive.close()
        return _text('application/vnd.openxmlformats-officedocument.wordprocessingml.document', source, value)


def default_processor() -> DocumentProcessor:
    return DocumentProcessor((TxtParser(), MarkdownParser(), HtmlParser(), PdfParser(), DocxParser()))


__all__ = ['DocxParser', 'HtmlParser', 'MarkdownParser', 'PdfParser', 'TxtParser', 'default_processor']
