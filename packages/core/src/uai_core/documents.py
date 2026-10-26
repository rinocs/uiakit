"""Document source, parser and normalization contracts.

Parsers receive host-owned bytes and never fetch URLs, execute scripts or call a
model. Limits are enforced before and after parsing; provenance stays in the
normalized text offsets.
"""
from dataclasses import dataclass
from typing import Protocol

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_CHARS = 2_000_000
MAX_PDF_PAGES = 2000
MAX_DOCX_ENTRIES = 1000
MAX_DOCX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_DOCX_TOTAL_BYTES = 64 * 1024 * 1024


class DocumentError(Exception):
    """Safe document failure; messages contain stable codes, not contents."""


class CorruptDocument(DocumentError):
    """The source cannot be decoded or parsed."""


class UnsupportedDocument(DocumentError):
    """The format/backend is known but not implemented or needs OCR."""


class DocumentLimit(DocumentError):
    """The source exceeds a byte, page or character limit."""


class UnsupportedBackend(DocumentError):
    """An optional OCR/SQL/web/Git backend is not installed or configured."""


@dataclass(frozen=True)
class DocumentPage:
    number: int
    text: str
    start: int
    end: int

    def __post_init__(self):
        if self.number < 1 or self.start < 0 or self.end < self.start:
            raise ValueError('invalid_document_page')


@dataclass(frozen=True)
class ParsedDocument:
    media_type: str
    source: str
    text: str
    pages: tuple[DocumentPage, ...]

    def __post_init__(self):
        if not self.media_type or not self.pages or len(self.text) > MAX_DOCUMENT_CHARS:
            raise ValueError('invalid_parsed_document')
        previous = -1
        for page in self.pages:
            if page.start < previous or page.end > len(self.text) or page.text != self.text[page.start:page.end]:
                raise ValueError('invalid_document_provenance')
            previous = page.end


def normalize_media_type(value: str) -> str:
    return value.split(';', 1)[0].strip().lower()


def normalize_text(value: str) -> str:
    value = value.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '')
    return '\n'.join(line.rstrip() for line in value.split('\n')).strip()


def document_from_pages(media_type: str, source: str, pages: list[tuple[int, str]]) -> ParsedDocument:
    """Join normalized pages and compute authoritative offsets into the joined text."""
    normalized = [(number, normalize_text(text)) for number, text in pages]
    parts: list[str] = []
    result = []
    offset = 0
    for index, (number, text) in enumerate(normalized):
        if index:
            offset += 2
        start = offset
        parts.append(text)
        offset += len(text)
        result.append(DocumentPage(number=number, text=text, start=start, end=offset))
    joined = '\n\n'.join(parts)
    if len(joined) > MAX_DOCUMENT_CHARS:
        raise DocumentLimit('document_too_large')
    return ParsedDocument(media_type=media_type, source=source, text=joined, pages=tuple(result))


class DocumentLoader(Protocol):
    media_type: str
    source: str

    def load(self) -> bytes: ...


class OcrProvider(Protocol):
    def extract(self, data: bytes, media_type: str) -> str: ...


class SqlConnector(Protocol):
    def fetch(self) -> bytes: ...


class WebLoader(DocumentLoader, Protocol):
    pass


class GitLoader(DocumentLoader, Protocol):
    pass


class DocumentParser(Protocol):
    media_types: frozenset[str]

    def parse(self, data: bytes, *, source: str = '') -> ParsedDocument: ...


@dataclass(frozen=True)
class BytesLoader:
    data: bytes
    media_type: str
    source: str = 'upload'

    def load(self) -> bytes:
        return self.data


class DocumentProcessor:
    def __init__(self, parsers: tuple[DocumentParser, ...] = ()):
        self._parsers: dict[str, DocumentParser] = {}
        for parser in parsers:
            self.register(parser)

    def register(self, parser: DocumentParser) -> None:
        for media_type in parser.media_types:
            normalized = normalize_media_type(media_type)
            if not normalized or normalized in self._parsers:
                raise ValueError('duplicate_parser')
            self._parsers[normalized] = parser

    def process(self, data: bytes, media_type: str, source: str = '') -> ParsedDocument:
        if not isinstance(data, bytes) or not data:
            raise CorruptDocument('empty_document')
        if len(data) > MAX_DOCUMENT_BYTES:
            raise DocumentLimit('document_too_large')
        normalized = normalize_media_type(media_type)
        parser = self._parsers.get(normalized)
        if parser is None:
            raise UnsupportedDocument('unsupported_media_type')
        result = parser.parse(data, source=source)
        if not result.text.strip():
            raise CorruptDocument('empty_document')
        if len(result.text) > MAX_DOCUMENT_CHARS:
            raise DocumentLimit('document_too_large')
        return result

    def process_loader(self, loader: DocumentLoader) -> ParsedDocument:
        return self.process(loader.load(), loader.media_type, loader.source)


__all__ = [
    'BytesLoader', 'CorruptDocument', 'DocumentError', 'DocumentLimit', 'DocumentLoader',
    'DocumentPage', 'DocumentParser', 'DocumentProcessor', 'GitLoader', 'MAX_DOCUMENT_BYTES',
    'MAX_DOCUMENT_CHARS', 'MAX_DOCX_ENTRIES', 'MAX_DOCX_ENTRY_BYTES', 'MAX_DOCX_TOTAL_BYTES',
    'MAX_PDF_PAGES', 'OcrProvider', 'ParsedDocument', 'SqlConnector', 'UnsupportedBackend',
    'UnsupportedDocument', 'WebLoader', 'document_from_pages', 'normalize_media_type',
    'normalize_text',
]
