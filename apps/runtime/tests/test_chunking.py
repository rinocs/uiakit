import hashlib

import pytest

from uai_core.chunks import Chunk, Chunker, ChunkingError, chunk_document
from uai_core.documents import document_from_pages


def parsed(text, pages=None):
    if pages is None:
        pages = [(1, text)]
    return document_from_pages('text/plain', 'fixture', pages)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_empty_and_short_documents():
    empty = parsed('')
    assert Chunker(10, 2).split(empty, document_hash=digest('')) == ()
    doc = parsed('hello')
    chunks = Chunker(10, 2).split(doc, document_hash=digest(doc.text))
    assert len(chunks) == 1
    assert chunks[0].text == 'hello' and chunks[0].start == 0 and chunks[0].end == 5
    assert chunks[0].page == 1 and chunks[0].index == 0
    assert len(chunks[0].id) == 64 and chunks[0].id == chunks[0].id


def test_long_text_overlap_and_last_fragment():
    text = 'abcdefghijklmnopqrstuvwxy'
    doc = parsed(text)
    chunks = Chunker(10, 3).split(doc, document_hash=digest(text))
    assert [chunk.text for chunk in chunks] == [text[0:10], text[7:17], text[14:24], text[21:25]]
    assert chunks[-1].end == len(text)
    assert all(doc.text[chunk.start:chunk.end] == chunk.text for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    short = parsed('abcdefgh')
    last = Chunker(6, 2).split(short, document_hash=digest(short.text))
    assert last[-1].text == 'efgh' and last[-1].end == 8


def test_page_boundaries_are_never_crossed():
    doc = parsed('', pages=[(1, 'AAAAA'), (2, 'BBBBB')])
    chunks = Chunker(4, 1).split(doc, document_hash=digest(doc.text))
    assert {chunk.page for chunk in chunks} == {1, 2}
    for chunk in chunks:
        assert chunk.text == doc.text[chunk.start:chunk.end]
        page = next(page for page in doc.pages if page.number == chunk.page)
        assert page.start <= chunk.start and chunk.end <= page.end
    assert all(chunk.end <= doc.pages[0].end for chunk in chunks if chunk.page == 1)
    assert all(chunk.start >= doc.pages[1].start for chunk in chunks if chunk.page == 2)


def test_unicode_offsets_are_code_points():
    text = '😀a😀b😀c'
    doc = parsed(text)
    chunks = Chunker(2, 1).split(doc, document_hash=digest(text))
    assert len(text) == 6
    assert all(doc.text[chunk.start:chunk.end] == chunk.text for chunk in chunks)
    assert ''.join(chunk.text for chunk in chunks[:1]) == '😀a'
    assert chunks[-1].end == 6


def test_stable_ids_are_identity_and_config_sensitive():
    doc = parsed('abcdefghij')
    first = Chunker(4, 1).split(doc, document_hash=digest(doc.text), document_version=1)
    again = Chunker(4, 1).split(doc, document_hash=digest(doc.text), document_version=1)
    assert [chunk.id for chunk in first] == [chunk.id for chunk in again]
    other = Chunker(4, 1).split(doc, document_hash=digest('different'))
    assert {chunk.id for chunk in first}.isdisjoint({chunk.id for chunk in other})
    changed = Chunker(5, 1).split(doc, document_hash=digest(doc.text))
    assert {chunk.id for chunk in first}.isdisjoint({chunk.id for chunk in changed})
    assert chunk_document(doc, document_hash=digest(doc.text), chunk_size=4, overlap=1) == first


def test_invalid_configuration_and_identity():
    for size, overlap in ((0, 0), (1, 1), (8001, 0), (10, -1)):
        with pytest.raises(ChunkingError):
            Chunker(size, overlap)
    doc = parsed('hello')
    with pytest.raises(ChunkingError):
        Chunker(4, 1).split(doc, document_hash='bad')
    with pytest.raises(ChunkingError):
        Chunker(4, 1).split(doc, document_hash=digest('hello'), document_version=0)


def test_property_coverage_for_lengths_sizes_and_overlaps():
    for length in range(0, 40):
        text = ''.join(chr(0x4e00 + (i % 50)) for i in range(length))
        doc = parsed(text)
        for size in range(1, 12):
            for overlap in range(0, size):
                chunks = Chunker(size, overlap).split(doc, document_hash=digest(text))
                if not text:
                    assert chunks == ()
                    continue
                assert chunks
                assert chunks[0].start == 0
                assert chunks[-1].end == length
                for chunk in chunks:
                    assert doc.text[chunk.start:chunk.end] == chunk.text
                    assert len(chunk.text) <= size
                    assert chunk.end - chunk.start == len(chunk.text)
                for left, right in zip(chunks, chunks[1:]):
                    assert right.start == left.end - overlap
