"""Deterministic chunking with stable IDs and provenance into normalized text."""
import hashlib
import re
from dataclasses import dataclass

from .documents import ParsedDocument

_HASH = re.compile(r'^[0-9a-f]{64}$')
MAX_CHUNK_SIZE = 8000


class ChunkingError(ValueError):
    """Invalid chunk configuration or provenance."""


@dataclass(frozen=True)
class Chunk:
    document_hash: str
    document_version: int
    page: int
    index: int
    start: int
    end: int
    text: str
    chunk_size: int
    overlap: int

    def __post_init__(self):
        if (not _HASH.fullmatch(self.document_hash) or self.document_version < 1
                or self.page < 1 or self.index < 0 or self.start < 0 or self.end <= self.start
                or not 1 <= self.chunk_size <= MAX_CHUNK_SIZE
                or self.overlap < 0 or self.overlap >= self.chunk_size
                or not self.text or len(self.text) != self.end - self.start):
            raise ChunkingError('invalid_chunk')

    @property
    def id(self) -> str:
        payload = (f'{self.document_hash}\x00{self.document_version}\x00{self.page}\x00'
                   f'{self.index}\x00{self.start}\x00{self.end}\x00{self.chunk_size}\x00{self.overlap}\x00'
                   ).encode() + self.text.encode('utf-8')
        return hashlib.sha256(payload).hexdigest()


class Chunker:
    def __init__(self, chunk_size: int, overlap: int):
        if (type(chunk_size) is not int or type(overlap) is not int
                or not 1 <= chunk_size <= MAX_CHUNK_SIZE or not 0 <= overlap < chunk_size):
            raise ChunkingError('invalid_chunk_configuration')
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, document: ParsedDocument, *, document_hash: str,
              document_version: int = 1) -> tuple[Chunk, ...]:
        if not _HASH.fullmatch(document_hash) or type(document_version) is not int or document_version < 1:
            raise ChunkingError('invalid_document_identity')
        chunks = []
        index = 0
        for page in document.pages:
            text = page.text
            cursor = 0
            while cursor < len(text):
                end = min(cursor + self.chunk_size, len(text))
                value = text[cursor:end]
                if not value:
                    break
                chunk = Chunk(document_hash=document_hash, document_version=document_version,
                              page=page.number, index=index, start=page.start + cursor,
                              end=page.start + end, text=value, chunk_size=self.chunk_size,
                              overlap=self.overlap)
                if document.text[chunk.start:chunk.end] != value:
                    raise ChunkingError('provenance_mismatch')
                chunks.append(chunk)
                index += 1
                if end == len(text):
                    break
                cursor = end - self.overlap
        return tuple(chunks)


def chunk_document(document: ParsedDocument, *, document_hash: str, chunk_size: int,
                   overlap: int, document_version: int = 1) -> tuple[Chunk, ...]:
    return Chunker(chunk_size, overlap).split(document, document_hash=document_hash,
                                               document_version=document_version)


__all__ = ['Chunk', 'Chunker', 'ChunkingError', 'MAX_CHUNK_SIZE', 'chunk_document']
